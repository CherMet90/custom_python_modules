import os
from dotenv import load_dotenv
import gitlab
from gitlab.exceptions import GitlabError

from custom_modules.errors import Error, NonCriticalError
from custom_modules.log import logger

# Загружаем .env файл
load_dotenv()

class GitLabConnector:
    # Получение переменных окружения
    # =====================================================================
    @staticmethod
    def __get_env_variable(variable_key):
        variable_value = os.environ.get(variable_key)
        if variable_value is None:
            raise ValueError(f"Missing environment variable: {variable_key}")
        return variable_value

    try:
        __gitlab_url = __get_env_variable("GITLAB_URL")
        __gitlab_token = __get_env_variable("GITLAB_PRIVATE_TOKEN")
    except ValueError as e:
        logger.error(f"{e}")
        __gitlab_url = None
        __gitlab_token = None
    # ====================================================================

    @classmethod
    def create_connection(cls):
        """Создает и аутентифицирует соединение с GitLab API."""
        if not cls.__gitlab_url or not cls.__gitlab_token:
            raise Error("GitLab URL or token not set. Please check environment variables.")

        try:
            cls.gitlab_connection = gitlab.Gitlab(url=cls.__gitlab_url, private_token=cls.__gitlab_token)
            cls.gitlab_connection.auth()
            logger.info("Connection to GitLab established")
            return cls.gitlab_connection
        except Exception as e:
            raise Error(f"Failed to connect to GitLab: {e}")

    @classmethod
    def get_project(cls, project_path):
        """Получает проект GitLab по его пути."""
        try:
            project = cls.gitlab_connection.projects.get(project_path)
            logger.debug(f"Project '{project.name_with_namespace}' found")
            return project
        except GitlabError as e:
            raise Error(f"Failed to get GitLab project '{project_path}': {e}")

    @classmethod
    def get_file_content(cls, project, file_path, ref='main'):
        try:
            file_obj = project.files.get(file_path=file_path, ref=ref)
            return file_obj.decode().decode('utf-8')
        except GitlabError as e:
            if e.response_code == 404:
                logger.warning(f"File '{file_path}' not found in project '{project.name}'.")
                return None
            raise NonCriticalError(f"GitLab API error for file '{file_path}': {e}", project.name, "get_file_content")

    @classmethod
    def get_repository_tree(cls, project, ref='main'):
        """
        Получает список каталогов верхнего уровня, которые мы считаем репозиториями.
        """
        try:
            tree = project.repository_tree(path='', ref=ref, recursive=False)
            # Возвращаем только имена каталогов
            return {item['name'] for item in tree if item['type'] == 'tree'}
        except GitlabError as e:
            raise Error(f"Failed to get repository tree for project '{project.name}': {e}")