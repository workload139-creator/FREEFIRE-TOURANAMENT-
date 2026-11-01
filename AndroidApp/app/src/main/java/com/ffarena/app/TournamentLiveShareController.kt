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
                    ScreenCaptureParams(
                        mediaProjectionPermissionResultData = permissionResultData,
                        onStop = {
                            // Android can revoke MediaProjection independently of the
                            // app. Tell the WebView so JOIN ROOM is not left in a false
                            // active state and the server session can be closed cleanly.
                            scope.launch {
                                val stoppedRoom = room
                                room = null
                                try {
                                    stoppedRoom?.disconnect()
                                    stoppedRoom?.release()
                                } catch (_: Exception) {
                                }
                                callback.onResult(
                                    false,
                                    "Android ne screen sharing rok di. Start Live AI dobara karein."
                                )
                            }
                        }
                    )
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

    fun setMicrophoneEnabled(enabled: Boolean, callback: Callback) {
        scope.launch {
            try {
                val activeRoom = room ?: throw IllegalStateException("Start Live screen sharing first.")
                val published = activeRoom.localParticipant.setMicrophoneEnabled(enabled)
                if (!published) {
                    throw IllegalStateException("LiveKit could not change microphone state.")
                }
                callback.onResult(
                    true,
                    if (enabled) "Mic ON. Admin can hear you." else "Mic OFF. Admin cannot hear you."
                )
            } catch (error: Exception) {
                callback.onResult(false, error.message ?: "Could not change microphone state.")
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
        scope.launch {
            val activeRoom = room
            room = null
            try {
                activeRoom?.localParticipant?.setScreenShareEnabled(false)
                activeRoom?.disconnect()
                activeRoom?.release()
            } catch (_: Exception) {
            } finally {
                scope.cancel()
            }
        }
    }
}