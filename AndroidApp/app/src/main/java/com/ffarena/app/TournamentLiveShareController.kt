package com.ffarena.app

import android.content.Context
import android.content.Intent
import io.livekit.android.LiveKit
import io.livekit.android.room.Room
import io.livekit.android.room.track.screencapture.ScreenCaptureParams
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/**
 * Native publisher for the player's explicitly consented Android screen share.
 * The server-issued, short-lived LiveKit token is supplied by the authenticated
 * FF Arena website; no API secret is stored in the APK.
 */
class TournamentLiveShareController(context: Context) {
    interface Callback {
        fun onResult(success: Boolean, message: String)
    }

    private val appContext = context.applicationContext
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var room: Room? = null
    private var busy = false

    fun start(
        serverUrl: String,
        participantToken: String,
        permissionResultData: Intent,
        callback: Callback
    ) {
        if (busy || room != null) {
            callback.onResult(false, "A Live session is already starting or active.")
            return
        }
        if (!serverUrl.startsWith("wss://") || participantToken.isBlank()) {
            callback.onResult(false, "The Live session credentials are invalid.")
            return
        }

        busy = true
        scope.launch {
            var createdRoom: Room? = null
            try {
                createdRoom = LiveKit.create(appContext)
                room = createdRoom
                createdRoom.connect(serverUrl, participantToken)
                val published = createdRoom.localParticipant.setScreenShareEnabled(
                    true,
                    ScreenCaptureParams(permissionResultData)
                )
                if (!published) {
                    throw IllegalStateException("LiveKit could not publish the screen share.")
                }
                callback.onResult(true, "FF Arena Live is sharing your screen.")
            } catch (error: Exception) {
                try {
                    createdRoom?.disconnect()
                    createdRoom?.release()
                } catch (_: Exception) {
                }
                if (room === createdRoom) room = null
                callback.onResult(false, error.message ?: "Could not start Live sharing.")
            } finally {
                busy = false
            }
        }
    }

    fun stop(callback: Callback? = null) {
        scope.launch {
            val activeRoom = room
            room = null
            try {
                activeRoom?.localParticipant?.setScreenShareEnabled(false)
                activeRoom?.disconnect()
                activeRoom?.release()
                callback?.onResult(true, "FF Arena Live sharing stopped.")
            } catch (error: Exception) {
                callback?.onResult(false, error.message ?: "Could not stop Live sharing cleanly.")
            }
        }
    }

    fun release() {
        stop()
        scope.cancel()
    }
}
