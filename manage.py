from common_models.common_models_setup import init_django

DEFAULT_DATABASE = {
    "ENGINE": "django.db.backends.postgresql_psycopg2",
    "NAME": "engfrosh_dev_2022_07_05",
    "USER": "engfrosh_bot",
    "PASSWORD": "there-exercise-fenegle",
    "HOST": "localhost",
    "PORT": "5432",
}

INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'common_models.apps.CommonModelsConfig', ]

if __name__ == "__main__":
    from django.core.management import execute_from_command_line

    init_django(installed_apps=INSTALLED_APPS, default_database=DEFAULT_DATABASE)
    execute_from_command_line()
