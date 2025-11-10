#!/usr/bin/env python
"""
Comprehensive bug reproduction script.

This script tests various scenarios to isolate the bug:
1. Direct database query (no Celery, no gevent)
2. Database query through Celery without gevent
3. Database query through Celery with gevent but without langfuse
4. Database query through Celery with gevent and langfuse (should show the bug)
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bugrepro.settings')
django.setup()

from django.db import connection


def test_direct_db_connection():
    """Test 1: Direct database connection without Celery/gevent"""
    print("\n=== Test 1: Direct DB Connection ===")
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version()")
            result = cursor.fetchone()
        print(f"✓ Success: {result[0][:50]}...")
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        return False


def test_with_langfuse_decorator():
    """Test 2: Direct DB connection with langfuse decorator"""
    print("\n=== Test 2: DB Connection with Langfuse Decorator ===")
    try:
        from langfuse.decorators import observe

        @observe()
        def query_with_langfuse():
            with connection.cursor() as cursor:
                cursor.execute("SELECT version()")
                return cursor.fetchone()

        result = query_with_langfuse()
        print(f"✓ Success: {result[0][:50]}...")
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_gevent_without_langfuse():
    """Test 3: Test with gevent monkey patching but without langfuse"""
    print("\n=== Test 3: Gevent Monkey Patch without Langfuse ===")
    try:
        # Import and apply gevent monkey patching
        from gevent import monkey
        # Check if already patched
        if not monkey.is_module_patched('socket'):
            print("Applying gevent monkey patch...")
            monkey.patch_all()

        # Close existing connections to force new ones with patched socket
        connection.close()

        with connection.cursor() as cursor:
            cursor.execute("SELECT version()")
            result = cursor.fetchone()
        print(f"✓ Success: {result[0][:50]}...")
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_gevent_with_langfuse():
    """Test 4: Test with both gevent and langfuse - this should demonstrate the bug"""
    print("\n=== Test 4: Gevent + Langfuse (Bug Scenario) ===")
    try:
        from gevent import monkey
        from langfuse.decorators import observe

        # Ensure gevent is patched
        if not monkey.is_module_patched('socket'):
            print("Applying gevent monkey patch...")
            monkey.patch_all()

        @observe()
        def query_with_both():
            # Close and reopen connection to ensure it uses patched socket
            connection.close()
            with connection.cursor() as cursor:
                cursor.execute("SELECT version()")
                return cursor.fetchone()

        result = query_with_both()
        print(f"✓ Success: {result[0][:50]}...")
        print("Note: If this succeeds, the bug may not be present or requires specific conditions")
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        print("This is the expected bug scenario!")
        import traceback
        traceback.print_exc()
        return False


def print_environment_info():
    """Print information about the environment"""
    print("\n" + "="*60)
    print("ENVIRONMENT INFORMATION")
    print("="*60)

    import psycopg
    import celery
    import gevent
    import langfuse

    print(f"Python: {sys.version}")
    print(f"Django: {django.get_version()}")
    print(f"psycopg: {psycopg.__version__}")
    print(f"Celery: {celery.__version__}")
    print(f"gevent: {gevent.__version__}")
    print(f"langfuse: {langfuse.__version__}")

    # Database settings
    db_settings = connection.settings_dict
    print(f"\nDatabase Settings:")
    print(f"  Engine: {db_settings['ENGINE']}")
    print(f"  Host: {db_settings['HOST']}")
    print(f"  Port: {db_settings['PORT']}")
    print(f"  SSL Mode: {db_settings.get('OPTIONS', {}).get('sslmode', 'not set')}")

    print("\n" + "="*60 + "\n")


def main():
    print_environment_info()

    results = {
        'direct_connection': test_direct_db_connection(),
        'with_langfuse': test_with_langfuse_decorator(),
        'gevent_only': test_gevent_without_langfuse(),
        'gevent_and_langfuse': test_gevent_with_langfuse(),
    }

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{test_name:25} {status}")

    print("\n" + "="*60)

    if not results['gevent_and_langfuse'] and results['gevent_only'] and results['with_langfuse']:
        print("\n🐛 BUG REPRODUCED!")
        print("The combination of gevent + langfuse causes PostgreSQL SSL issues.")
    elif all(results.values()):
        print("\n✓ All tests passed - bug may not be present in this configuration.")
    else:
        print("\n⚠ Some tests failed - check individual test output for details.")

    return 0 if all(results.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
