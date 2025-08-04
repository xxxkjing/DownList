# DownList
 
 
> An application to download unlimited amount of music from Netease playlist.
> 一个可以无限制下载网易云音乐歌单的应用
 

## 界面

![](assets/display.png)

### 特色

**免登录 绕过每月400首额度 直接保存为 `MP3`、`FLAC`格式**

## 开始准备

你需要准备：

1. 一台正常的电脑 安装了一个正常的浏览器
2. 网易云音乐账号（建议用有黑胶VIP的，没有VIP会有歌曲下载不了）
3. 一个正常的脑子

## 使用方法

1. 到Release或 [蓝奏云（密码h3bn）](https://xia-jing.lanzoup.com/iRvGh32mio8d)中下载（大小68.9MB）

2. 打开网页版，获取并复制网易云音乐的用户Cookie：下图中的`MUSIC_U`

   ![](assets/cookie.png)

3. 下载项目中的cookie.txt演示文件（仅供格式展示），覆盖原来的`MUSIC_U`变量

4. 运行程序，填入歌单链接，点击解析，选择下载音质与下载目录，点击下载

5. Enjoy :D



## 核心函数

### 1. **Cookie 管理**

- **`CookieManager` 类**：负责读取和解析存储在 `cookie.txt` 文件中的 Cookie，用于身份验证。

### 2. **网易云音乐 API 请求**

- **`post` 函数**：发送 POST 请求到网易云音乐 API，携带必要的请求头和 Cookie。
- **`url_v1`、`name_v1` 和 `lyric_v1` 函数**：分别用于获取歌曲的下载链接、歌曲信息和歌词。

### 3. **下载逻辑**

- `download_playlist` 方法：主下载逻辑，解析歌单、创建下载目录并循环下载每首歌曲。
  - **下载控制**：支持暂停、继续和取消下载，使用 `is_paused` 标志控制下载状态。

### 4. **下载歌曲**

- `download_song` 方法：负责下载单首歌曲，包括获取音频 URL、下载音频文件和歌词。
  - **音频文件下载**：调用 `download_file` 方法，使用 `requests` 库流式下载音频文件，并更新下载进度。

### 5. **文件元数据**

- **`add_metadata` 方法**：在下载完成后，将歌曲的元数据（如标题、艺术家、专辑、封面）嵌入到音频文件中。使用 `mutagen` 库处理不同格式的音频文件（FLAC 和 MP3）。

### 6. **用户界面**

- 使用 `flet` 库创建用户界面，包括输入框、按钮和进度条，允许用户输入歌单 URL、选择音质、选择下载目录等。

### 7. **多线程**

- **下载线程**：使用 `threading` 模块在后台处理下载任务，确保界面响应流畅。

### 8. **日志记录**

- 使用 `logging` 模块记录下载过程中的各种信息和错误，便于调试和追踪。



## ToDo

等到有100个Star再来更新......

- [ ] 优化软件体积大小
- [ ] 优化jy*等格式文件
- [ ] 优化jy*等格式元数据写入
- [ ] 实现多线程下载



## 备注

1. 本项目仅供学习，不为盈利。请不要用于商业用途，或者在咸鱼上转卖，传播等请联系本人，不要随意传播。
2. 本项目基于 [NeteaseUrl](https://github.com/Suxiaoqinx/Netease_url) ，用AI二次开发 感谢 [Suxiaoqinx大大](https://github.com/Suxiaoqinx) ；以及后面可能不会在这个项目上花太多时间了，欢迎大佬fork过去继续开发
3. 如果你很闲，你可以来逛一逛[我的博客](https://xia.shfu.cn/)
