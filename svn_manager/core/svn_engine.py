"""
SVN 核心引擎 - 封装所有 SVN 命令行操作
"""
import subprocess
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class SVNStatus(Enum):
    NORMAL = "normal"
    MODIFIED = "modified"
    ADDED = "added"
    DELETED = "deleted"
    CONFLICTED = "conflicted"
    UNVERSIONED = "unversioned"
    MISSING = "missing"
    REPLACED = "replaced"
    IGNORED = "ignored"
    EXTERNAL = "external"
    OBSTRUCTED = "obstructed"
    UNKNOWN = "unknown"


STATUS_CHAR_MAP = {
    ' ': SVNStatus.NORMAL,
    'M': SVNStatus.MODIFIED,
    'A': SVNStatus.ADDED,
    'D': SVNStatus.DELETED,
    'C': SVNStatus.CONFLICTED,
    '?': SVNStatus.UNVERSIONED,
    '!': SVNStatus.MISSING,
    'R': SVNStatus.REPLACED,
    'I': SVNStatus.IGNORED,
    'X': SVNStatus.EXTERNAL,
    '~': SVNStatus.OBSTRUCTED,
}

STATUS_CHAR_TO_WORD = {
    ' ': 'normal', 'M': 'modified', 'A': 'added', 'D': 'deleted',
    'C': 'conflicted', '?': 'unversioned', '!': 'missing', 'R': 'replaced',
    'I': 'ignored', 'X': 'external', '~': 'obstructed',
}


@dataclass
class SVNFileStatus:
    path: str
    status: SVNStatus
    prop_status: SVNStatus = SVNStatus.NORMAL
    locked: bool = False
    switched: bool = False
    revision: str = ""
    author: str = ""
    is_dir: bool = False


@dataclass
class SVNLogEntry:
    revision: str
    author: str
    date: str
    message: str
    changed_paths: list = field(default_factory=list)


@dataclass
class SVNInfo:
    path: str
    url: str
    repo_root: str
    repo_uuid: str
    revision: str
    node_kind: str
    last_changed_rev: str
    last_changed_date: str
    last_changed_author: str
    wc_root: str = ""


class SVNEngine:
    """SVN 命令封装引擎"""

    def __init__(self, svn_binary: str = "svn"):
        self.svn_binary = svn_binary
        self._find_svn()

    def _find_svn(self):
        """自动查找 svn 可执行文件"""
        candidates = [
            "/opt/homebrew/bin/svn",
            "/usr/local/bin/svn",
            "/usr/bin/svn",
        ]
        for c in candidates:
            if os.path.exists(c):
                self.svn_binary = c
                return
        # fallback
        try:
            result = subprocess.run(["which", "svn"], capture_output=True, text=True)
            if result.returncode == 0:
                self.svn_binary = result.stdout.strip()
        except Exception:
            pass

    # 需要网络的子命令集合，统一加 --non-interactive 防止打包后挂起
    _NETWORK_CMDS = {
        "checkout", "update", "commit", "switch", "merge",
        "info", "log", "diff", "list", "cat", "blame",
        "lock", "unlock", "export", "copy", "move",
    }

    def _build_auth_args(self, username: str = None, password: str = None,
                         no_auth_cache: bool = False) -> list:
        """构建认证相关参数列表"""
        args = []
        if username:
            args += ["--username", username]
        if password:
            args += ["--password", password]
        if no_auth_cache:
            args.append("--no-auth-cache")
        return args

    def _run(self, args: list, cwd: str = None, timeout: int = 60,
             env: dict = None) -> tuple[int, str, str]:
        """执行 SVN 命令，返回 (returncode, stdout, stderr)。
        对网络类命令自动添加 --non-interactive，避免打包后挂起等待终端输入。
        """
        # 在子命令后插入 --non-interactive（若尚未包含）
        full_args = list(args)
        if full_args and full_args[0] in self._NETWORK_CMDS:
            if "--non-interactive" not in full_args:
                full_args.insert(1, "--non-interactive")

        cmd = [self.svn_binary] + full_args
        run_env = os.environ.copy()
        # 强制英文输出，便于解析
        run_env["LANG"] = "en_US.UTF-8"
        run_env["LC_ALL"] = "en_US.UTF-8"
        if env:
            run_env.update(env)
        try:
            result = subprocess.run(
                cmd, cwd=cwd, capture_output=True,
                text=True, timeout=timeout, env=run_env
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except FileNotFoundError:
            return -2, "", f"SVN binary not found: {self.svn_binary}"
        except Exception as e:
            return -3, "", str(e)

    def _run_stream(self, args: list, line_callback=None,
                    cwd: str = None, timeout: int = 600,
                    env: dict = None) -> tuple[int, str]:
        """流式执行 SVN 命令，逐行回调输出，返回 (returncode, all_output)
        line_callback(line: str) 每收到一行时调用。
        对网络类命令自动添加 --non-interactive。
        """
        full_args = list(args)
        if full_args and full_args[0] in self._NETWORK_CMDS:
            if "--non-interactive" not in full_args:
                full_args.insert(1, "--non-interactive")

        cmd = [self.svn_binary] + full_args
        run_env = os.environ.copy()
        run_env["LANG"] = "en_US.UTF-8"
        run_env["LC_ALL"] = "en_US.UTF-8"
        if env:
            run_env.update(env)

        import threading
        collected = []
        try:
            proc = subprocess.Popen(
                cmd, cwd=cwd, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, env=run_env,
                bufsize=1,
            )

            def _reader():
                for line in proc.stdout:
                    line = line.rstrip("\n")
                    collected.append(line)
                    if line_callback:
                        line_callback(line)

            t = threading.Thread(target=_reader, daemon=True)
            t.start()
            t.join(timeout=timeout)
            if t.is_alive():
                proc.kill()
                return -1, "\n".join(collected) + "\n[超时终止]"
            proc.wait()
            return proc.returncode, "\n".join(collected)
        except FileNotFoundError:
            msg = f"SVN binary not found: {self.svn_binary}"
            if line_callback:
                line_callback(msg)
            return -2, msg
        except Exception as e:
            msg = str(e)
            if line_callback:
                line_callback(msg)
            return -3, msg

    # ── 基础查询 ──────────────────────────────────────────────────────

    def is_working_copy(self, path: str) -> bool:
        """检查路径是否为 SVN 工作副本"""
        rc, out, err = self._run(["info", path], timeout=10)
        return rc == 0

    def get_info(self, path: str) -> Optional[SVNInfo]:
        """获取路径的 SVN 信息"""
        rc, out, err = self._run(["info", "--xml", path], timeout=15)
        if rc != 0:
            return None
        try:
            root = ET.fromstring(out)
            entry = root.find(".//entry")
            if entry is None:
                return None
            url = entry.findtext("url", "")
            repo = entry.find("repository")
            repo_root = repo.findtext("root", "") if repo is not None else ""
            repo_uuid = repo.findtext("uuid", "") if repo is not None else ""
            commit = entry.find("commit")
            last_rev = commit.get("revision", "") if commit is not None else ""
            last_date = commit.findtext("date", "") if commit is not None else ""
            last_author = commit.findtext("author", "") if commit is not None else ""
            wc_info = entry.find("wc-info")
            wc_root = wc_info.findtext("wcroot-abspath", "") if wc_info is not None else ""
            return SVNInfo(
                path=path,
                url=url,
                repo_root=repo_root,
                repo_uuid=repo_uuid,
                revision=entry.get("revision", ""),
                node_kind=entry.get("kind", ""),
                last_changed_rev=last_rev,
                last_changed_date=last_date,
                last_changed_author=last_author,
                wc_root=wc_root,
            )
        except ET.ParseError:
            return None

    def get_status(self, path: str, show_updates: bool = False,
                   verbose: bool = False) -> list[SVNFileStatus]:
        """获取工作副本状态列表
        verbose=True 时使用 --verbose 显示全部受控文件（含 normal 状态）
        """
        args = ["status", "--xml"]
        if show_updates:
            args.append("-u")
        if verbose:
            args.append("--verbose")
        args.append(path)
        rc, out, err = self._run(args, timeout=60)
        if rc != 0:
            return []
        return self._parse_status_xml(out, path)

    def _parse_status_xml(self, xml_str: str, base_path: str) -> list[SVNFileStatus]:
        items = []
        try:
            root = ET.fromstring(xml_str)
            for entry in root.findall(".//entry"):
                fpath = entry.get("path", "")
                wc_status = entry.find("wc-status")
                if wc_status is None:
                    continue
                item_attr = wc_status.get("item", "normal")
                prop_attr = wc_status.get("props", "none")
                locked = wc_status.get("wc-locked", "false") == "true"
                switched = wc_status.get("switched", "false") == "true"

                status_map = {
                    "normal": SVNStatus.NORMAL,
                    "modified": SVNStatus.MODIFIED,
                    "added": SVNStatus.ADDED,
                    "deleted": SVNStatus.DELETED,
                    "conflicted": SVNStatus.CONFLICTED,
                    "unversioned": SVNStatus.UNVERSIONED,
                    "missing": SVNStatus.MISSING,
                    "replaced": SVNStatus.REPLACED,
                    "ignored": SVNStatus.IGNORED,
                    "external": SVNStatus.EXTERNAL,
                    "obstructed": SVNStatus.OBSTRUCTED,
                }
                status = status_map.get(item_attr, SVNStatus.UNKNOWN)
                prop_status_val = status_map.get(prop_attr, SVNStatus.NORMAL)

                commit = wc_status.find("commit")
                rev = commit.get("revision", "") if commit is not None else ""
                author = commit.findtext("author", "") if commit is not None else ""

                items.append(SVNFileStatus(
                    path=fpath,
                    status=status,
                    prop_status=prop_status_val,
                    locked=locked,
                    switched=switched,
                    revision=rev,
                    author=author,
                    is_dir=os.path.isdir(fpath),
                ))
        except ET.ParseError:
            pass
        return items

    def get_diff(self, path: str, revision1: str = None, revision2: str = None,
                 diff_cmd: str = None) -> str:
        """获取 diff 输出"""
        args = ["diff"]
        if revision1 and revision2:
            args += ["-r", f"{revision1}:{revision2}"]
        elif revision1:
            args += ["-r", revision1]
        args.append(path)
        rc, out, err = self._run(args, timeout=30)
        return out if rc == 0 else err

    def get_diff_two_paths(self, path1: str, path2: str) -> str:
        args = ["diff", path1, path2]
        rc, out, err = self._run(args, timeout=30)
        return out if rc == 0 else err

    def get_diff_for_revision(self, path: str, revision: str,
                              repo_file_path: str = None) -> str:
        """获取某次提交的 diff（rev-1:rev）。
        path: 本地工作副本路径（目录或文件）
        revision: 版本号字符串
        repo_file_path: 可选，仓库内相对路径（如 /trunk/src/foo.py），
                        若提供则只 diff 该文件
        """
        try:
            prev_rev = str(int(revision) - 1)
        except ValueError:
            prev_rev = "PREV"
        rev_range = f"{prev_rev}:{revision}"

        if repo_file_path:
            # 通过仓库 URL 做 diff，获取 repo_root + file_path 组合 URL
            info = self.get_info(path)
            if info and info.repo_root:
                file_url = info.repo_root.rstrip("/") + "/" + repo_file_path.lstrip("/")
                args = ["diff", "-r", rev_range, file_url]
                rc, out, err = self._run(args, timeout=60)
                if rc == 0:
                    return out
            # 降级：diff 整个路径
        args = ["diff", "-r", rev_range, path]
        rc, out, err = self._run(args, timeout=60)
        return out if rc == 0 else err

    def get_log(self, path: str, limit: int = 50, revision: str = None,
                verbose: bool = False) -> list[SVNLogEntry]:
        """获取提交日志"""
        args = ["log", "--xml", f"--limit={limit}"]
        if verbose:
            args.append("-v")
        if revision:
            args += ["-r", revision]
        args.append(path)
        rc, out, err = self._run(args, timeout=30)
        if rc != 0:
            return []
        return self._parse_log_xml(out)

    def _parse_log_xml(self, xml_str: str) -> list[SVNLogEntry]:
        entries = []
        try:
            root = ET.fromstring(xml_str)
            for le in root.findall("logentry"):
                rev = le.get("revision", "")
                author = le.findtext("author", "")
                date = le.findtext("date", "")
                msg = le.findtext("msg", "")
                paths = []
                for p in le.findall(".//path"):
                    paths.append({
                        "action": p.get("action", ""),
                        "path": p.text or "",
                    })
                entries.append(SVNLogEntry(
                    revision=rev, author=author,
                    date=date, message=msg, changed_paths=paths
                ))
        except ET.ParseError:
            pass
        return entries

    # ── 写操作 ────────────────────────────────────────────────────────

    def update(self, path: str, revision: str = "HEAD",
               username: str = None, password: str = None,
               no_auth_cache: bool = False) -> tuple[bool, str]:
        """更新工作副本"""
        args = ["update", f"-r{revision}", "--force"]
        args += self._build_auth_args(username, password, no_auth_cache)
        args.append(path)
        rc, out, err = self._run(args, timeout=120)
        msg = out + err
        return rc == 0, msg

    def commit(self, paths: list[str], message: str,
               keep_locks: bool = False,
               username: str = None, password: str = None,
               no_auth_cache: bool = False) -> tuple[bool, str]:
        """提交更改"""
        args = ["commit", "-m", message]
        if keep_locks:
            args.append("--keep-locks")
        args += self._build_auth_args(username, password, no_auth_cache)
        args += paths
        rc, out, err = self._run(args, timeout=120)
        return rc == 0, out + err

    def add(self, paths: list[str], no_ignore: bool = False) -> tuple[bool, str]:
        """添加文件到版本控制"""
        args = ["add"]
        if no_ignore:
            args.append("--no-ignore")
        args += paths
        rc, out, err = self._run(args, timeout=30)
        return rc == 0, out + err

    def revert(self, paths: list[str], recursive: bool = False) -> tuple[bool, str]:
        """还原文件修改"""
        args = ["revert"]
        if recursive:
            args.append("-R")
        args += paths
        rc, out, err = self._run(args, timeout=30)
        return rc == 0, out + err

    def delete(self, paths: list[str], force: bool = False) -> tuple[bool, str]:
        """删除文件"""
        args = ["delete"]
        if force:
            args.append("--force")
        args += paths
        rc, out, err = self._run(args, timeout=30)
        return rc == 0, out + err

    def copy(self, src: str, dst: str, message: str = "") -> tuple[bool, str]:
        """复制/分支"""
        args = ["copy", src, dst]
        if message:
            args += ["-m", message]
        rc, out, err = self._run(args, timeout=60)
        return rc == 0, out + err

    def move(self, src: str, dst: str, message: str = "") -> tuple[bool, str]:
        """移动/重命名"""
        args = ["move", src, dst]
        if message:
            args += ["-m", message]
        rc, out, err = self._run(args, timeout=30)
        return rc == 0, out + err

    def mkdir(self, path: str, message: str = "") -> tuple[bool, str]:
        """创建目录"""
        args = ["mkdir", path]
        if message:
            args += ["-m", message]
        rc, out, err = self._run(args, timeout=30)
        return rc == 0, out + err

    def checkout(self, url: str, path: str, revision: str = "HEAD",
                 depth: str = "infinity",
                 username: str = None, password: str = None,
                 no_auth_cache: bool = False,
                 line_callback=None) -> tuple[bool, str]:
        """检出仓库，支持流式输出回调和认证参数"""
        args = ["checkout", f"-r{revision}", f"--depth={depth}",
                "--non-interactive"]
        if username:
            args += ["--username", username]
        if password:
            args += ["--password", password]
        if no_auth_cache:
            args.append("--no-auth-cache")
        args += [url, path]
        if line_callback:
            rc, out = self._run_stream(args, line_callback=line_callback,
                                       timeout=600)
            return rc == 0, out
        rc, out, err = self._run(args, timeout=600)
        return rc == 0, out + err

    def resolve(self, paths: list[str], accept: str = "working") -> tuple[bool, str]:
        """解决冲突"""
        args = ["resolve", f"--accept={accept}"] + paths
        rc, out, err = self._run(args, timeout=30)
        return rc == 0, out + err

    def lock(self, paths: list[str], message: str = "",
             force: bool = False,
             username: str = None, password: str = None,
             no_auth_cache: bool = False) -> tuple[bool, str]:
        """锁定文件"""
        args = ["lock"]
        if message:
            args += ["-m", message]
        if force:
            args.append("--force")
        args += self._build_auth_args(username, password, no_auth_cache)
        args += paths
        rc, out, err = self._run(args, timeout=30)
        return rc == 0, out + err

    def unlock(self, paths: list[str], force: bool = False,
               username: str = None, password: str = None,
               no_auth_cache: bool = False) -> tuple[bool, str]:
        """解锁文件"""
        args = ["unlock"]
        if force:
            args.append("--force")
        args += self._build_auth_args(username, password, no_auth_cache)
        args += paths
        rc, out, err = self._run(args, timeout=30)
        return rc == 0, out + err

    def cleanup(self, path: str) -> tuple[bool, str]:
        """清理工作副本"""
        args = ["cleanup", path]
        rc, out, err = self._run(args, timeout=60)
        return rc == 0, out + err

    def switch(self, path: str, url: str, revision: str = "HEAD",
               username: str = None, password: str = None,
               no_auth_cache: bool = False) -> tuple[bool, str]:
        """切换工作副本到另一个 URL"""
        args = ["switch", f"-r{revision}"]
        args += self._build_auth_args(username, password, no_auth_cache)
        args += [url, path]
        rc, out, err = self._run(args, timeout=120)
        return rc == 0, out + err

    def merge(self, path: str, url_or_rev: str, revision: str = None,
              dry_run: bool = False,
              username: str = None, password: str = None,
              no_auth_cache: bool = False) -> tuple[bool, str]:
        """合并"""
        args = ["merge"]
        if dry_run:
            args.append("--dry-run")
        if revision:
            args += ["-r", revision]
        args += self._build_auth_args(username, password, no_auth_cache)
        args += [url_or_rev, path]
        rc, out, err = self._run(args, timeout=120)
        return rc == 0, out + err

    def export(self, url_or_path: str, dest: str,
               revision: str = "HEAD") -> tuple[bool, str]:
        """导出"""
        args = ["export", f"-r{revision}", "--force", url_or_path, dest]
        rc, out, err = self._run(args, timeout=120)
        return rc == 0, out + err

    def propset(self, prop: str, value: str, path: str) -> tuple[bool, str]:
        """设置属性"""
        args = ["propset", prop, value, path]
        rc, out, err = self._run(args, timeout=15)
        return rc == 0, out + err

    def propget(self, prop: str, path: str) -> str:
        """获取属性"""
        rc, out, err = self._run(["propget", prop, path], timeout=15)
        return out.strip() if rc == 0 else ""

    def proplist(self, path: str) -> dict:
        """列出所有属性"""
        rc, out, err = self._run(["proplist", "--xml", path], timeout=15)
        props = {}
        if rc == 0:
            try:
                root = ET.fromstring(out)
                for target in root.findall("target"):
                    for prop in target.findall("property"):
                        name = prop.get("name", "")
                        value = self.propget(name, path)
                        props[name] = value
            except ET.ParseError:
                pass
        return props

    def cat(self, path: str, revision: str = None) -> str:
        """获取文件内容"""
        args = ["cat"]
        if revision:
            args += ["-r", revision]
        args.append(path)
        rc, out, err = self._run(args, timeout=30)
        return out if rc == 0 else ""

    def blame(self, path: str) -> str:
        """逐行显示提交人"""
        rc, out, err = self._run(["blame", path], timeout=30)
        return out if rc == 0 else err

    def get_working_copy_root(self, path: str) -> Optional[str]:
        """获取工作副本根目录"""
        info = self.get_info(path)
        if info and info.wc_root:
            return info.wc_root
        # 逐级向上查找
        current = os.path.abspath(path)
        while True:
            if os.path.exists(os.path.join(current, ".svn")):
                parent = os.path.dirname(current)
                if parent == current:
                    return current
                if not os.path.exists(os.path.join(parent, ".svn")):
                    return current
                current = parent
            else:
                return None

    def list_remote(self, url: str, revision: str = "HEAD") -> list[dict]:
        """列出远程目录"""
        args = ["list", "--xml", f"-r{revision}", url]
        rc, out, err = self._run(args, timeout=30)
        items = []
        if rc == 0:
            try:
                root = ET.fromstring(out)
                for entry in root.findall(".//entry"):
                    kind = entry.get("kind", "file")
                    name = entry.findtext("name", "")
                    commit = entry.find("commit")
                    rev = commit.get("revision", "") if commit is not None else ""
                    author = commit.findtext("author", "") if commit is not None else ""
                    date = commit.findtext("date", "") if commit is not None else ""
                    size = entry.findtext("size", "")
                    items.append({
                        "kind": kind, "name": name,
                        "revision": rev, "author": author,
                        "date": date, "size": size,
                    })
            except ET.ParseError:
                pass
        return items

    def get_changed_files(self, path: str) -> list[SVNFileStatus]:
        """只返回有变更的文件（不含 normal 状态）"""
        all_status = self.get_status(path)
        return [s for s in all_status
                if s.status not in (SVNStatus.NORMAL, SVNStatus.IGNORED, SVNStatus.EXTERNAL)]

    # ── 凭证管理 ──────────────────────────────────────────────────────

    def list_auth_cache(self) -> list[dict]:
        """列出本地所有已缓存的 SVN 凭证。
        优先使用 `svn auth`（SVN 1.9+），兜底扫描文件系统。
        返回 [{"realm": str, "username": str, "source": "svn"|"file"}, ...]
        """
        entries = []

        # 方式一：svn auth（1.9+）
        rc, out, err = self._run(["auth"], timeout=10)
        if rc == 0 and out.strip():
            current: dict = {}
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("Authentication realm:"):
                    if current:
                        entries.append(current)
                    current = {"realm": line.split(":", 1)[1].strip(),
                               "username": "", "source": "svn"}
                elif line.startswith("Username:"):
                    current["username"] = line.split(":", 1)[1].strip()
            if current:
                entries.append(current)
            return entries

        # 方式二：扫描 ~/.subversion/auth/svn.simple/
        auth_dir = os.path.expanduser("~/.subversion/auth/svn.simple")
        if not os.path.isdir(auth_dir):
            return entries
        for fname in os.listdir(auth_dir):
            fpath = os.path.join(auth_dir, fname)
            try:
                with open(fpath, "r", errors="replace") as f:
                    content = f.read()
                realm = ""
                username = ""
                lines = content.splitlines()
                i = 0
                while i < len(lines):
                    line = lines[i]
                    if line.strip() == "svn:realmstring":
                        i += 1
                        if i < len(lines):
                            # 下一行是长度，再下一行是值
                            i += 1
                            if i < len(lines):
                                realm = lines[i].strip()
                    elif line.strip() == "username":
                        i += 1
                        if i < len(lines):
                            i += 1
                            if i < len(lines):
                                username = lines[i].strip()
                    i += 1
                entries.append({
                    "realm": realm,
                    "username": username,
                    "source": "file",
                    "_file": fpath,
                })
            except Exception:
                pass
        return entries

    def clear_auth_cache(self, realm_or_url: str = "") -> tuple[bool, str]:
        """清除本地已缓存的 SVN 凭证。
        realm_or_url 为空时清除全部；否则按 realm / URL 前缀匹配删除。
        优先使用 `svn auth --remove`，兜底删除对应文件。
        返回 (ok, message)
        """
        removed = []
        errors = []

        # 方式一：svn auth --remove（SVN 1.9+）
        rc_test, _, _ = self._run(["auth", "--help"], timeout=5)
        # svn auth 支持 --remove 时 help 不会报 unknown subcommand
        args = ["auth", "--remove"]
        if realm_or_url:
            args.append(realm_or_url)
        else:
            args.append("*")
        rc, out, err = self._run(args, timeout=10)
        if rc == 0:
            msg = out.strip() or f"已清除凭证（匹配: {realm_or_url or '全部'}）"
            return True, msg

        # 方式二：直接删除文件
        auth_dir = os.path.expanduser("~/.subversion/auth/svn.simple")
        if not os.path.isdir(auth_dir):
            return True, "未找到凭证缓存目录（~/.subversion/auth/svn.simple），无需清除"

        for fname in os.listdir(auth_dir):
            fpath = os.path.join(auth_dir, fname)
            try:
                if realm_or_url:
                    with open(fpath, "r", errors="replace") as f:
                        content = f.read()
                    if realm_or_url.lower() not in content.lower():
                        continue
                os.remove(fpath)
                removed.append(fname)
            except Exception as e:
                errors.append(str(e))

        if errors:
            return False, "部分删除失败:\n" + "\n".join(errors)
        if not removed:
            return True, f"未找到匹配的凭证缓存（{realm_or_url or '全部'}）"
        return True, f"已删除 {len(removed)} 条凭证缓存记录"
