# SVN Free

基于 **Tauri 2 + Vue 3 + TypeScript** 的 macOS SVN 图形管理工具。  
通过系统已安装的 `svn` 命令行驱动工作副本管理、浏览、提交与预览。

## 功能

- **左侧工作副本**
  - 新增：选择本地已有 SVN 工作副本目录加入列表
  - 检出：输入 SVN 地址与本地目录，执行 `svn checkout`
  - 删除：仅从列表移除，不删除本地文件
- **中间文件浏览**
  - 列表 / 图标 / 分栏 三种视图
  - 双击进入文件夹，面包屑导航
  - 显示 SVN 状态（M/A/D/? 等）
  - 右键：提交、更新、还原、删除、DIFF、日志、属性、在 Finder 显示
- **右侧预览**
  - 文本、代码、图片预览
  - 文件夹与二进制文件提示

## 环境要求

- macOS
- Node.js 18+
- Rust（Tauri 构建需要）
- Subversion CLI：`brew install svn`

## 开发

```bash
npm install
npm run tauri dev
```

## 打包 macOS 应用

```bash
npm run tauri build
```

产物一般在：

```text
src-tauri/target/release/bundle/macos/SVN Free.app
src-tauri/target/release/bundle/dmg/
```

## 说明

- 工作副本列表保存在系统应用数据目录：`~/Library/Application Support/svn-free/workspaces.json`
- 所有 SVN 操作都调用本机 `svn`，请确保命令可用：`svn --version`
