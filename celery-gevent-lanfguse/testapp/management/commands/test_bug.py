from django.core.management.base import BaseCommand
from django.db import connection
from gevent import monkey
import sys


class Command(BaseCommand):
    help = 'Test the gevent + langfuse + psycopg3 SSL bug'

    def add_arguments(self, parser):
        parser.add_argument(
            '--with-gevent',
            action='store_true',
            help='Apply gevent monkey patching',
        )
        parser.add_argument(
            '--with-langfuse',
            action='store_true',
            help='Use langfuse decorator',
        )

    def handle(self, *args, **options):
        use_gevent = options['with_gevent']
        use_langfuse = options['with_langfuse']

        self.stdout.write(self.style.SUCCESS('Testing database connection...'))
        self.stdout.write(f'Gevent: {use_gevent}')
        self.stdout.write(f'Langfuse: {use_langfuse}')
        self.stdout.write('')

        # Apply gevent monkey patching if requested
        if use_gevent:
            if not monkey.is_module_patched('socket'):
                self.stdout.write('Applying gevent monkey patch...')
                monkey.patch_all()
            else:
                self.stdout.write('Gevent already patched')

        # Define the test function
        def test_query():
            connection.close()  # Force new connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT version()")
                result = cursor.fetchone()
            return result[0]

        # Wrap with langfuse if requested
        if use_langfuse:
            try:
                from langfuse import observe
                test_query = observe()(test_query)
                self.stdout.write('Applied langfuse decorator')
            except ImportError:
                self.stdout.write(self.style.ERROR('Langfuse not available'))
                return

        # Execute the test
        try:
            result = test_query()
            self.stdout.write(self.style.SUCCESS(f'\n✓ Success!'))
            self.stdout.write(f'PostgreSQL version: {result[:80]}...')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n✗ Failed!'))
            self.stdout.write(self.style.ERROR(f'Error: {e}'))
            import traceback
            self.stdout.write(traceback.format_exc())
            sys.exit(1)
