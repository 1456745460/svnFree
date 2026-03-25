"""
文件变化监控器 - 监控工作副本文件变化，触发状态刷新
"""
import os
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from PyQt6.QtCore import QObject, pyqtSignal


class _SVNWatchHandler(FileSystemEventHandler):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self._timer = None
        self._lock = threading.Lock()

    def _debounce(self):
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(0.8, self.callback)
            self._timer.daemon = True
            self._timer.start()

    def on_any_event(self, event: FileSystemEvent):
        # 忽略 .svn 内部变化（避免递归触发）
        path = event.src_path
        if "/.svn/" in path or path.endswith("/.svn"):
            return
        # 忽略隐藏文件
        if os.path.basename(path).startswith("."):
            return
        self._debounce()


class FileWatcher(QObject):
    """监控工作副本目录，文件变化时发出信号"""
    changed = pyqtSignal(str)  # 发送变化的工作副本路径

    def __init__(self, parent=None):
        super().__init__(parent)
        self._observer = Observer()
        self._watches: dict[str, object] = {}
        self._started = False

    def watch(self, path: str):
        if path in self._watches:
            return
        handler = _SVNWatchHandler(lambda p=path: self.changed.emit(p))
        try:
            watch = self._observer.schedule(handler, path, recursive=True)
            self._watches[path] = watch
            if not self._started:
                self._observer.start()
                self._started = True
        except Exception as e:
            print(f"[FileWatcher] watch error: {e}")

    def unwatch(self, path: str):
        if path in self._watches:
            try:
                self._observer.unschedule(self._watches.pop(path))
            except Exception:
                pass

    def stop(self):
        try:
            if self._started:
                self._observer.stop()
                self._observer.join(timeout=3)
        except Exception:
            pass
