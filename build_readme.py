import json
import os
import pathlib
import re

import feedparser
import httpx
from python_graphql_client import GraphqlClient

root = pathlib.Path(__file__).parent.resolve()
client = GraphqlClient(endpoint="https://api.github.com/graphql")


TOKEN = os.environ.get("TOKEN", "")


def replace_chunk(content, marker, chunk, inline=False):
    r = re.compile(
        f"<!\-\- {marker} starts \-\->.*<!\-\- {marker} ends \-\->", re.DOTALL
    )
    if not inline:
        chunk = f"\n{chunk}\n"
    chunk = f"<!-- {marker} starts -->{chunk}<!-- {marker} ends -->"
    return r.sub(chunk, content)


organization_graphql = """
  organization(login: "retrofor") {
    repositories(first: 100, privacy: PUBLIC) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        name
        description
        url
        releases(orderBy: {field: CREATED_AT, direction: DESC}, first: 1) {
          totalCount
          nodes {
            name
            publishedAt
            url
          }
        }
      }
    }
  }
"""


def make_query(after_cursor=None, include_organization=False):
    return (
        """
query {
  ORGANIZATION
  viewer {
    repositories(first: 100, privacy: PUBLIC, after: AFTER) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        name
        description
        url
        releases(orderBy: {field: CREATED_AT, direction: DESC}, first: 1) {
          totalCount
          nodes {
            name
            publishedAt
            url
          }
        }
      }
    }
  }
}
""".replace(
            "AFTER", f'"{after_cursor}"' if after_cursor else "null"
        )
    ).replace("ORGANIZATION", organization_graphql if include_organization else "")


def fetch_releases(oauth_token):
    repos = []
    releases = []
    repo_names = {"playing-with-actions"}  # Skip this one
    has_next_page = True
    after_cursor = None

    first = True

    while has_next_page:
        data = client.execute(
            query=make_query(after_cursor, include_organization=first),
            headers={"Authorization": f"Bearer {oauth_token}"},
        )
        first = False
        print()
        print(json.dumps(data, indent=4))
        print()
        repo_nodes = data["data"]["viewer"]["repositories"]["nodes"]
        if "organization" in data["data"]:
            repo_nodes += data["data"]["organization"]["repositories"]["nodes"]
        for repo in repo_nodes:
            if repo["releases"]["totalCount"] and repo["name"] not in repo_names:
                repos.append(repo)
                repo_names.add(repo["name"])
                try:
                    releases.append(
                        {
                            "repo": repo["name"],
                            "repo_url": repo["url"],
                            "description": repo["description"],
                            "release": repo["releases"]["nodes"][0]["name"]
                            .replace(repo["name"], "")
                            .strip(),
                            "published_at": repo["releases"]["nodes"][0]["publishedAt"],
                            "published_day": repo["releases"]["nodes"][0][
                                "publishedAt"
                            ].split("T")[0],
                            "url": repo["releases"]["nodes"][0]["url"],
                            "total_releases": repo["releases"]["totalCount"],
                        }
                    )
                except:
                    releases.append(
                        {
                            "repo": repo["name"],
                            "repo_url": repo["url"],
                            "description": repo["description"],
                            "release": repo["releases"]["nodes"][0]["name"]
                            .replace(repo["name"], "")
                            .strip(),
                            "published_at": "Near Future",
                            "published_day": "Near Future",
                            "url": repo["releases"]["nodes"][0]["url"],
                            "total_releases": repo["releases"]["totalCount"],
                        }
                    )
        after_cursor = data["data"]["viewer"]["repositories"]["pageInfo"]["endCursor"]
        has_next_page = after_cursor
    return releases


# def fetch_tils():
#     sql = """
#         select path, replace(title, '_', '\_') as title, url, topic, slug, created_utc
#         from til order by created_utc desc limit 5
#     """.strip()
#     return httpx.get(
#         "https://til.simonwillison.net/tils.json",
#         params={"sql": sql, "_shape": "array",},
#     ).json()


def fetch_blog_entries():
    entries = feedparser.parse("https://academic.jyunko.cn/feed.xml")["entries"]
    return [
        {
            "title": entry["title"],
            "url": entry["id"],
            "published": entry["published"].split("T")[0],
            "summary": entry["summary"],
        }
        for entry in entries
    ]


def fetch_fm_entries():
    entries = feedparser.parse("https://fm.jyunko.cn/feed.xml")["entries"]
    return [
        {
            "title": entry["title"],
            "url": entry["id"],
            "published": entry["published"].split("T")[0],
            "categlory": entry["tags"][1]["term"],
        }
        for entry in entries
    ]


def fetch_diary_entries():
    entries = feedparser.parse("https://diary.jyunko.cn/feed.xml")["entries"]
    print(entries)
    return [
        {
            "title": entry["title"],
            "url": entry["id"] + '.html',
            "published": entry["published"].split("T")[0]
            # "summary": entry["summary"]
        }
        for entry in entries
    ]


if __name__ == "__main__":
    readme = root / "README.md"
    project_releases = root / "releases.md"
    releases = fetch_releases(TOKEN)
    releases.sort(key=lambda r: r["published_at"], reverse=True)
    md = "\n\n".join(
        [
            "[{repo} {release}]({url}) - {published_day}".format(**release)
            for release in releases[:10]
        ]
    )
    readme_contents = readme.open().read()
    rewritten = replace_chunk(readme_contents, "recent_releases", md)

    #     Write out full project-releases.md file
    project_releases_md = "\n".join(
        [
            (
                (
                    "* **[{repo}]({repo_url})**: [{release}]({url}) {total_releases_md} - {published_day}\n"
                    "<br />{description}"
                ).format(
                    total_releases_md=f'- ([{release["total_releases"]} releases total]({release["repo_url"]}/releases)) '
                    if release["total_releases"] > 1
                    else "",
                    **release,
                )
            )
            for release in releases
        ]
    )
    project_releases_content = project_releases.open().read()
    project_releases_content = replace_chunk(
        project_releases_content, "recent_releases", project_releases_md
    )
    project_releases_content = replace_chunk(
        project_releases_content, "project_count", str(len(releases)), inline=True
    )
    project_releases_content = replace_chunk(
        project_releases_content,
        "releases_count",
        str(sum(r["total_releases"] for r in releases)),
        inline=True,
    )
    project_releases.open("w").write(project_releases_content)

    #     tils = fetch_tils()
    #     tils_md = "\n\n".join(
    #         [
    #             "[{title}](https://til.simonwillison.net/{topic}/{slug}) - {created_at}".format(
    #                 title=til["title"],
    #                 topic=til["topic"],
    #                 slug=til["slug"],
    #                 created_at=til["created_utc"].split("T")[0],
    #             )
    #             for til in tils
    #         ]
    #     )
    #     rewritten = replace_chunk(rewritten, "tils", tils_md)
    # blog
    entries = fetch_blog_entries()[:7]
    entries_md = "\n\n".join(
        [
            '<details><summary>{published} <a href="{url}">{title}</a></summary><p>{summary}</p></details>'.format(
                **entry
            )
            for entry in entries
        ]
    )
    print()
    print(entries_md)
    print()
    rewritten = replace_chunk(rewritten, "blog", entries_md)
    # fm
    fm_entries = fetch_fm_entries()[:6]
    fm_entries_md = "\n\n".join(
        [
            '<details open="true"><summary>{published} {categlory}</summary><li><a href="{url}">{title}</a></li></details>'.format(
                **entry
            )
            for entry in fm_entries
        ]
    )
    print()
    print(fm_entries_md)
    print()
    rewritten = replace_chunk(rewritten, "fm", fm_entries_md)
    # diary
    diary_entries = fetch_diary_entries()[:5]
    diary_entries_md = "\n\n".join(
        [
            '<details open="true"><summary>{published}</summary><li><a href="{url}">{title}</a></li></details>'.format(
                **entry
            )
            for entry in diary_entries
        ]
    )
    print()
    print(diary_entries_md)
    print()
    rewritten = replace_chunk(rewritten, "diary", diary_entries_md)

    readme.open("w").write(rewritten)
