import logging
from typing import Tuple, Optional

import requests

from bubo.config import Config
from bubo.storage import Storage

logger = logging.getLogger(__name__)


async def ensure_community_exists(
    community: tuple, config: Config
) -> Tuple[str, Optional[str]]:
    """
    Maintains a community.
    """
    dbid, name, alias, title, icon, description = community
    logger.info(f"Ensuring community {name} ({alias}) exists")

    api_prefix = f"{config.homeserver_url}/_matrix/client/r0"
    headers = {
        "Authorization": f"Bearer {config.user_token}",
    }
    # Check if community exists
    response = requests.get(
        f"{api_prefix}/groups/+{alias}:{config.server_name}/profile",
        headers=headers,
    )
    if response.status_code == 200:
        # TODO ensure name + title
        return "exists", None
    else:
        # Try create the community
        logger.info(f"Community {name} not found, will try to create")
        response = requests.post(
            f"{api_prefix}/create_group",
            json={
                "localpart": alias,
                "profile": {
                    "name": name,
                    "short_description": title,
                    "long_description": description,
                },
            },
            headers=headers,
        )
        if response.status_code > 201:
            return "error", f"{response.status_code} / {response.content}"
        return "created", None


async def maintain_configured_communities(store: Storage, config: Config):
    """
    Maintains the list of configured communities.

    Creates if missing. Corrects if details are not correct.
    Maintains rooms in the communities.
    """
    logger.info("Starting maintaining of communities")

    results = store.cursor.execute(
        """
        select * from communities
    """
    )

    communities = results.fetchall()
    for community in communities:
        try:
            await ensure_community_exists(community, config)
        except Exception as e:
            logger.error(f"Error with community '{community[2]}': {e}")
