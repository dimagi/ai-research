#!/usr/bin/env python
"""
Inspect SSL context behavior with gevent + langfuse + psycopg3.

This tool helps diagnose SSL context issues by showing:
- SSL module state
- Thread-local storage
- Connection SSL parameters
- gevent greenlet context
"""

import os
import sys
import ssl
import threading

# Apply gevent monkey patching
from gevent import monkey
monkey.patch_all(aggressive=True)

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bugrepro.settings')
django.setup()

import gevent
from django.db import connection
from testapp.langfuse import get_random_langfuse_account


def inspect_ssl_module():
    """Inspect SSL module state."""
    print("\n" + "="*60)
    print("SSL MODULE INSPECTION")
    print("="*60)

    print(f"\nSSL module: {ssl}")
    print(f"SSL version: {ssl.OPENSSL_VERSION}")
    print(f"SSL version info: {ssl.OPENSSL_VERSION_INFO}")

    # Check if SSL module is patched
    print(f"\nIs SSL module patched by gevent? {monkey.is_module_patched('ssl')}")

    # Default SSL context
    try:
        ctx = ssl.create_default_context()
        print(f"\nDefault SSL context created: {ctx}")
        print(f"  Protocol: {ctx.protocol}")
        print(f"  Check hostname: {ctx.check_hostname}")
        print(f"  Verify mode: {ctx.verify_mode}")
        print(f"  CA certs loaded: {ctx.ca_certs is not None or 'default'}")
    except Exception as e:
        print(f"\nError creating default SSL context: {e}")

    print("="*60 + "\n")


def inspect_threading():
    """Inspect threading and greenlet context."""
    print("\n" + "="*60)
    print("THREADING/GREENLET INSPECTION")
    print("="*60)

    print(f"\nCurrent thread: {threading.current_thread()}")
    print(f"Thread name: {threading.current_thread().name}")
    print(f"Thread ident: {threading.current_thread().ident}")

    try:
        import greenlet
        print(f"\nCurrent greenlet: {greenlet.getcurrent()}")
        print(f"Greenlet parent: {greenlet.getcurrent().parent}")
    except ImportError:
        print("\ngreenlet module not available")

    print(f"\nThread-local storage test:")
    local = threading.local()
    local.test_value = "thread_local_data"
    print(f"  Set thread-local value: {local.test_value}")

    # Test in greenlet
    def check_thread_local():
        try:
            value = local.test_value
            print(f"  Greenlet can access thread-local: {value}")
        except AttributeError:
            print(f"  Greenlet CANNOT access thread-local (expected with gevent)")

    greenlet = gevent.spawn(check_thread_local)
    greenlet.join()

    print("="*60 + "\n")


def inspect_db_connection():
    """Inspect database connection SSL parameters."""
    print("\n" + "="*60)
    print("DATABASE CONNECTION INSPECTION")
    print("="*60)

    print("\nDatabase settings:")
    db_settings = connection.settings_dict
    print(f"  ENGINE: {db_settings['ENGINE']}")
    print(f"  HOST: {db_settings['HOST']}")
    print(f"  PORT: {db_settings['PORT']}")
    print(f"  OPTIONS: {db_settings.get('OPTIONS', {})}")

    print("\nAttempting database connection...")
    try:
        with connection.cursor() as cursor:
            # Get SSL information from PostgreSQL
            cursor.execute("""
                SELECT
                    ssl_is_used() as ssl_enabled,
                    version() as pg_version,
                    current_database() as database,
                    pg_backend_pid() as backend_pid
            """)
            row = cursor.fetchone()
            print(f"  ✓ Connection successful")
            print(f"  SSL enabled: {row[0]}")
            print(f"  PostgreSQL version: {row[1][:50]}...")
            print(f"  Database: {row[2]}")
            print(f"  Backend PID: {row[3]}")

            # Try to get SSL details
            try:
                cursor.execute("""
                    SELECT
                        ssl_version() as ssl_version,
                        ssl_cipher() as ssl_cipher,
                        ssl_client_dn() as client_dn
                """)
                ssl_info = cursor.fetchone()
                print(f"\n  SSL Version: {ssl_info[0]}")
                print(f"  SSL Cipher: {ssl_info[1]}")
                print(f"  SSL Client DN: {ssl_info[2] or 'None'}")
            except Exception as e:
                print(f"\n  Could not retrieve SSL details: {e}")

    except Exception as e:
        print(f"  ✗ Connection failed: {e}")
        import traceback
        traceback.print_exc()

    print("="*60 + "\n")


def inspect_with_langfuse():
    """Test connection with langfuse tracing."""
    print("\n" + "="*60)
    print("CONNECTION WITH LANGFUSE TRACING")
    print("="*60)

    print("\nAttempting connection with langfuse trace...")
    try:
        tracer = get_random_langfuse_account()
        with tracer.trace("ssl_inspection") as span:
            connection.close()  # Force new connection

            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        pg_backend_pid(),
                        ssl_is_used(),
                        ssl_version(),
                        ssl_cipher()
                """)
                pid, ssl_used, ssl_ver, ssl_cipher = cursor.fetchone()

                print(f"  ✓ Connection with langfuse successful")
                print(f"  Backend PID: {pid}")
                print(f"  SSL Used: {ssl_used}")
                print(f"  SSL Version: {ssl_ver}")
                print(f"  SSL Cipher: {ssl_cipher}")

                span.set_outputs({
                    "pid": pid,
                    "ssl_used": ssl_used,
                    "ssl_version": ssl_ver,
                })

    except Exception as e:
        print(f"  ✗ Connection with langfuse failed: {e}")
        import traceback
        traceback.print_exc()

    print("="*60 + "\n")


def inspect_psycopg():
    """Inspect psycopg3 internals."""
    print("\n" + "="*60)
    print("PSYCOPG3 INSPECTION")
    print("="*60)

    try:
        import psycopg
        print(f"\npsycopg version: {psycopg.__version__}")

        # Get connection details
        from django.db import connection as django_conn
        conn = django_conn.connection
        if conn:
            print(f"\nConnection object: {conn}")
            print(f"Connection class: {type(conn)}")

            # Try to access SSL info
            try:
                info = conn.info
                print(f"\nConnection info:")
                print(f"  Backend PID: {info.backend_pid}")
                print(f"  Status: {info.status}")
                print(f"  Transaction status: {info.transaction_status}")
                print(f"  SSL: {info.ssl_in_use}")
                if info.ssl_in_use:
                    print(f"  SSL attribute: {info.ssl_attribute('protocol')}")
                    print(f"  SSL cipher: {info.ssl_attribute('cipher')}")
            except Exception as e:
                print(f"  Could not get connection info: {e}")
        else:
            print("\nNo active connection")

    except ImportError:
        print("\npsycopg module not found")
    except Exception as e:
        print(f"\nError inspecting psycopg: {e}")
        import traceback
        traceback.print_exc()

    print("="*60 + "\n")


def main():
    print("\n" + "="*70)
    print(" "*15 + "SSL CONTEXT DIAGNOSTIC TOOL")
    print("="*70)

    print("\nMonkey patching status:")
    for mod in ['socket', 'ssl', 'thread', 'time', 'select', 'os']:
        patched = monkey.is_module_patched(mod)
        status = "✓" if patched else "✗"
        print(f"  {status} {mod}")

    # Run inspections
    inspect_ssl_module()
    inspect_threading()
    inspect_psycopg()
    inspect_db_connection()
    inspect_with_langfuse()

    print("\n" + "="*70)
    print(" "*20 + "DIAGNOSTIC COMPLETE")
    print("="*70 + "\n")

    return 0


if __name__ == '__main__':
    sys.exit(main())
