# demo_algo_blocker

本包用于演示 L1 **正式分散树**阻断项：

- 源码在 `NIMM/02diagnostic/demo_algo_blocker/`（不再要求包内再套 `src/`、`cli/`）
- 故意缺少仓库根级配套：`cli|test|docs|nbs|resource/02diagnostic/demo_algo_blocker/`
- 且无继承 `BasePlugin` / `PostProcessingPlugin` 的具体插件类

预期：`MISSING_REQUIRED_DIR_OFFICIAL` + `NO_CONCRETE_PLUGIN`。
