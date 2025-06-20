# constants.py

# --- Web Application Settings ---
APP_VERSION = "2.2.1"  # 或者你的实际版本号
DEBUG_MODE = False      # 开发时设为 True，部署到生产环境时应设为 False
WEB_APP_PORT = 5257    # Web UI 监听的端口

# --- 功能模式切换开关 ---
CONFIG_SECTION_FEATURES = "Features"
CONFIG_OPTION_USE_SA_MODE = "use_sa_mode"

# --- 数据库设置 ---
DB_NAME = "emby_actor_processor.sqlite" # 数据库文件名 (也可以在这里定义，然后在 web_app.py 中引用)

# --- 配置文件名 ---
CONFIG_FILE_NAME = "config.ini"
DOUBAN_API_AVAILABLE = True

# --- 用户认证常量 ---
CONFIG_SECTION_AUTH = "Authentication"
CONFIG_OPTION_AUTH_ENABLED = "auth_enabled"
CONFIG_OPTION_AUTH_USERNAME = "username"
DEFAULT_USERNAME = "admin"
# --- 新增：翻译缓存配置 ---
CONFIG_OPTION_TRANSLATION_FAILURE_RETRY_DAYS = "translation_failure_retry_days"
DEFAULT_TRANSLATION_FAILURE_RETRY_DAYS = 1 # 默认1天后重试
# --- 翻译引擎 ---
# 你可以定义所有可用的翻译引擎列表，供设置页面选择
AVAILABLE_TRANSLATOR_ENGINES = ['bing', 'google', 'baidu', 'alibaba', 'youdao', 'tencent']
# 默认的翻译引擎顺序
DEFAULT_TRANSLATOR_ENGINES_ORDER = ['bing', 'google', 'baidu']

#本地数据源配置
CONFIG_SECTION_LOCAL_DATA = "LocalDataSource" # 新的节名
CONFIG_OPTION_LOCAL_DATA_PATH = "local_data_path" # 本地数据源根路径
DEFAULT_LOCAL_DATA_PATH = "" # 默认空，表示未配置

CONFIG_FILE_NAME = "config.ini"
DB_NAME = "emby_actor_processor.sqlite"

# --- 豆瓣处理模式 ---
DOMESTIC_SOURCE_MODE_LOCAL_THEN_ONLINE = "local_then_online"
DOMESTIC_SOURCE_MODE_ONLINE_ONLY = "online_only"
DOMESTIC_SOURCE_MODE_LOCAL_ONLY = "local_only"
DOMESTIC_SOURCE_MODE_DISABLED = "disabled_douban" # 明确禁用
DEFAULT_DOMESTIC_SOURCE_MODE = DOMESTIC_SOURCE_MODE_LOCAL_THEN_ONLINE
# 用于设置页面的选项
DOMESTIC_SOURCE_OPTIONS = [
    {"value": DOMESTIC_SOURCE_MODE_LOCAL_THEN_ONLINE, "text": "豆瓣本地优先，在线备选 (推荐)"},
    {"value": DOMESTIC_SOURCE_MODE_ONLINE_ONLY, "text": "仅在线豆瓣API"},
    {"value": DOMESTIC_SOURCE_MODE_LOCAL_ONLY, "text": "仅豆瓣本地数据 (神医刮削)"},
    {"value": DOMESTIC_SOURCE_MODE_DISABLED, "text": "禁用豆瓣数据源"}
]


# --- API 冷却时间默认值 (如果 core_processor 或其他地方需要) ---
DEFAULT_API_COOLDOWN_SECONDS_FALLBACK = 1.0
MAX_API_COOLDOWN_SECONDS_FALLBACK = 5.0
COOLDOWN_INCREMENT_SECONDS_FALLBACK = 0.5

# --- TMDB API Key (如果 core_processor 或其他地方需要) ---
FALLBACK_TMDB_API_KEY = "" # 最好让用户在配置中填写

# --- 配置文件的节和选项名 (保持与你的 load_config/save_config 一致) ---
CONFIG_SECTION_EMBY = "Emby"
CONFIG_OPTION_EMBY_SERVER_URL = "emby_server_url"
CONFIG_OPTION_EMBY_API_KEY = "emby_api_key"
CONFIG_OPTION_EMBY_USER_ID = "emby_user_id"
CONFIG_OPTION_EMBY_LIBRARIES_TO_PROCESS = "libraries_to_process"
# ✨ 新增处理选项的节和选项常量 ✨
CONFIG_SECTION_PROCESSING = "Processing"
CONFIG_OPTION_REFRESH_AFTER_UPDATE = "refresh_emby_after_update"
CONFIG_OPTION_PROCESS_EPISODES = "process_episodes"
CONFIG_OPTION_SYNC_IMAGES = "sync_images" # <--- 在这里定义新选项的常量
# ... 其他配置常量 ...
CONFIG_SECTION_TMDB = "TMDB"
CONFIG_OPTION_TMDB_API_KEY = "tmdb_api_key"
CONFIG_SECTION_API_DOUBAN = "DoubanAPI"
CONFIG_OPTION_DOUBAN_DEFAULT_COOLDOWN = "api_douban_default_cooldown_seconds"
CONFIG_SECTION_TRANSLATION = "Translation"
CONFIG_OPTION_TRANSLATOR_ENGINES = "translator_engines_order"
CONFIG_SECTION_DOMESTIC_SOURCE = "DomesticSource"
CONFIG_OPTION_DOMESTIC_SOURCE_MODE = "domestic_source_mode"
DEFAULT_MIN_SCORE_FOR_REVIEW = 6.0
CONFIG_SECTION_GENERAL = "General"
CONFIG_OPTION_MAX_ACTORS_TO_PROCESS = "max_actors_to_process"
DEFAULT_MAX_ACTORS_TO_PROCESS = 50 # 最多演员数量默认值
CONFIG_SECTION_SCHEDULER = "Scheduler"
# ★★★ 新增追剧定时任务的常量 ★★★
CONFIG_OPTION_SCHEDULE_WATCHLIST_ENABLED = "schedule_watchlist_enabled"
CONFIG_OPTION_SCHEDULE_WATCHLIST_CRON = "schedule_watchlist_cron"
DEFAULT_SCHEDULE_WATCHLIST_CRON = "0 */6 * * *" # 默认每6小时执行一次
# ✨✨✨ AI 翻译相关的常量 ✨✨✨
CONFIG_SECTION_AI_TRANSLATION = "AITranslation"
CONFIG_OPTION_AI_TRANSLATION_ENABLED = "ai_translation_enabled"
CONFIG_OPTION_AI_PROVIDER = "ai_provider"
CONFIG_OPTION_AI_API_KEY = "ai_api_key"
CONFIG_OPTION_AI_MODEL_NAME = "ai_model_name"
CONFIG_OPTION_AI_BASE_URL = "ai_base_url"
CONFIG_OPTION_AI_TRANSLATION_PROMPT = "ai_translation_prompt"
DEFAULT_AI_TRANSLATION_PROMPT = """你是一位专业的影视剧翻译专家，尤其擅长将英文或拼音格式的人名和角色名，翻译成符合中文影视圈习惯的、最常见的官方或通用译名。

你的任务是：
1.  **只返回翻译后的中文文本**。不要包含任何解释、标签或标点符号，例如不要说“翻译结果是：”或返回带引号的文本。
2.  **识别并翻译人名**：如果输入是 `Yoon Se-ri` 或 `Zhang San` 这样的拼音/罗马音，请尽力翻译成最通用的中文人名，例如“尹世理”或“张三”。
3.  **处理混合内容**：如果输入是 `Maj. Sophie E. Jean`，请翻译成“苏菲·E·让少校”，保留军衔等上下文。
4.  **保持原文**：如果输入的内容已经是中文，或者是一个你无法识别为有效人名/角色名的无意义词汇，请直接返回原文。
5.  **力求精准**：翻译结果必须追求“信、达、雅”，优先使用官方译名。
6.  **对于一些中国耳熟能详的如“MJ、DJ、M、Q”等超短大写英文名缩写，直接返回原文。"""
# --- 演员状态文本映射 (用于 /api/search_media) ---
ACTOR_STATUS_TEXT_MAP = {
    "ok": "已处理",
    "name_untranslated": "演员名未翻译",
    "character_untranslated": "角色名未翻译",
    "name_char_untranslated": "演员名和角色名均未翻译",
    "pending_translation": "待翻译",
    "parent_failed": "媒体项处理失败",
    "unknown": "未知状态"
}
# API Source Map (如果未来增加其他API来源)
SOURCE_API_MAP = {
    "Douban": {
        "name": "豆瓣",
        "search_types": {
            "movie": {"title": "电影", "season": False},
            "tv": {"title": "电视剧", "season": True},
        },
    },
}
#时区
TIMEZONE = "Asia/Shanghai"

# 中文语言代码列表 (用于判断文本是否为中文)
CHINESE_LANG_CODES = ["zh", "zh-cn", "zh-hans", "cmn", "yue", "cn", "zh-sg", "zh-tw", "zh-hk"]