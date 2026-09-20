# 来源与复用边界

- ComfyUI core: 387f98aa2822f684b8597959a52a467d88cc4806。
- AnimaYume 作者模型：https://huggingface.co/duongve/AnimaYume
- Qwen 官方 ComfyUI 教程：https://docs.comfy.org/tutorials/image/qwen/qwen-image-edit-2511
- VNCCS：https://github.com/AHEKOT/ComfyUI_VNCCS ，固定 2206d1743f7920a7b9a21f80f03777d9ddce74c3。复用已安装的 Qwen 编码节点。
- VNCCS Utils：https://github.com/AHEKOT/ComfyUI_VNCCS_Utils ，固定 70b752f2f1ac7a6aa22aa9418f730195c3cef58b。复用 Pose Studio；局部编辑借鉴检测、上下文裁剪、Qwen、回贴结构，但自行实现显式检测失败和精确像素边界节点。
- st-chatu8：https://github.com/damoshen123/st-chatu8 。借鉴角色/上下文/模板分层、参数化工作流、返回生成记录。后端独立实现，没有复制其插件代码。
- Impact Pack/Subpack、RMBG 的提交与最小加载补丁见 nodes-manifest.json。上游许可证保持在服务器克隆目录；RMBG BiRefNet 集成源码为 GPL-3.0，其模型来源及许可见上游。项目没有把这些上游节点重新授权为自身代码。
- 额外权重固定 revision、大小与 SHA256见 additional-models-manifest.json。SAM 使用 Meta 官方下载 URL，同名模型公开 SHA256 作为完整性校验来源。

后端代码、CLI 与 AIGC_LocalEdit 为本次独立实现。工作流及样例包含明确来源与实际参数，不将参考项目功能包装为本次首创。
