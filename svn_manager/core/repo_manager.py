"""
仓库管理器 - 管理所有已添加的工作副本
"""
import json
import os
from dataclasses import dataclass, asdict, field
from typing import Optional


CONFIG_DIR = os.path.expanduser("~/.svnfree")
CONFIG_FILE = os.path.join(CONFIG_DIR, "repos.json")


@dataclass
class Repository:
    path: str
    name: str = ""
    url: str = ""
    last_updated: str = ""
    auto_refresh: bool = True
    color_tag: str = ""   # 用于 UI 颜色标签

    def __post_init__(self):
        if not self.name:
            self.name = os.path.basename(self.path.rstrip("/"))


class RepoManager:
    """管理工作副本列表，持久化到 ~/.svnfree/repos.json"""

    def __init__(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        self.repos: list[Repository] = []
        self.load()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.repos = [Repository(**item) for item in data]
            except Exception:
                self.repos = []

    def save(self):
        try:
            data = [asdict(r) for r in self.repos]
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[RepoManager] save error: {e}")

    def add(self, path: str, url: str = "", name: str = "") -> Repository:
        path = os.path.abspath(path)
        # 去重
        for r in self.repos:
            if r.path == path:
                return r
        repo = Repository(path=path, url=url, name=name or os.path.basename(path))
        self.repos.append(repo)
        self.save()
        return repo

    def remove(self, path: str):
        path = os.path.abspath(path)
        self.repos = [r for r in self.repos if r.path != path]
        self.save()

    def get(self, path: str) -> Optional[Repository]:
        path = os.path.abspath(path)
        for r in self.repos:
            if r.path == path:
                return r
        return None

    def update_url(self, path: str, url: str):
        repo = self.get(path)
        if repo:
            repo.url = url
            self.save()

    def update_name(self, path: str, name: str):
        repo = self.get(path)
        if repo:
            repo.name = name
            self.save()

    def all_paths(self) -> list[str]:
        return [r.path for r in self.repos]
