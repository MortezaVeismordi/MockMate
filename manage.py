"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path


def main():
    """Run administrative tasks."""
    # Set default Django settings module
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? "
            "Did you forget to activate a virtual environment?"
        ) from exc

    # Helpful messages for common commands
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "runserver":
            print("🚀 Starting development server...")
        elif command == "migrate":
            print("🔄 Applying database migrations...")
        elif command == "makemigrations":
            print("📝 Creating migration files...")
        elif command == "collectstatic":
            print("📦 Collecting static files...")
        elif command == "check":
            print("✅ Running system checks...")

    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    # Ensure manage.py runs from project root
    current_path = Path(__file__).resolve().parent
    sys.path.append(str(current_path))

    main()