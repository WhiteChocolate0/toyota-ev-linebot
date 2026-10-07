import pytest

from app.config import Settings
from app.services.environment_safety import EnvironmentSafetyError, require_nonproduction_database_write, validate_database_environment


PROD = "extkwpghjfttamontqkl"
DEV = "devproject1234567890"


def configured(env: str, project: str) -> Settings:
    role = "production" if env == "production" else "development"
    return Settings(app_env=env, database_role=role, supabase_url=f"https://{project}.supabase.co", current_supabase_project_ref=project, production_supabase_project_ref=PROD)


def test_development_role_cannot_connect_to_configured_future_production():
    with pytest.raises(EnvironmentSafetyError):
        validate_database_environment(configured("development", PROD))


def test_test_cannot_write_to_production():
    settings = configured("test", PROD)
    with pytest.raises(EnvironmentSafetyError):
        require_nonproduction_database_write(settings, operation="integration test")


def test_production_cannot_connect_to_nonproduction_project():
    with pytest.raises(EnvironmentSafetyError):
        validate_database_environment(configured("production", DEV))


def test_development_dev_project_is_valid():
    result = require_nonproduction_database_write(configured("development", DEV), operation="seed")
    assert result.project_ref == DEV


def test_mvp_project_is_valid_for_development_role_without_production_project():
    settings = configured("development", PROD).model_copy(update={"production_supabase_project_ref": ""})
    result = validate_database_environment(settings)
    assert result.app_env == "development"
    assert result.database_role == "development"
    assert result.project_ref == PROD


def test_development_environment_rejects_production_role():
    settings = configured("development", DEV).model_copy(update={"database_role": "production"})
    with pytest.raises(EnvironmentSafetyError):
        validate_database_environment(settings)


def test_production_environment_rejects_development_role():
    settings = configured("production", PROD).model_copy(update={"database_role": "development"})
    with pytest.raises(EnvironmentSafetyError):
        validate_database_environment(settings)
