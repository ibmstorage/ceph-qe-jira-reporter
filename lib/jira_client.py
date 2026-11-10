from jira import JIRA

from config.settings import JiraConfig


def get_jira_client(config: JiraConfig):
    if not config.token:
        raise ValueError(
            "JIRA_TOKEN is required. Set env var or add jira_token to config file."
        )
    if config.email:
        return JIRA(server=config.server, basic_auth=(config.email, config.token))
    return JIRA(server=config.server, token_auth=config.token)
