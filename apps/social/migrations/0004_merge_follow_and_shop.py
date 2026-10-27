from django.db import migrations


class Migration(migrations.Migration):
    """
    Merge the independent Follow and shop/FF Tick migration branches.
    No database operations are performed by this migration.
    """
    dependencies = [
        ("social", "0002_follow"),
        ("social", "0003_playershopwallet_shop_payment_gifts_withdrawals"),
    ]

    operations = []
