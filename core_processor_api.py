# core_processor_api.py
import time
import re
import os
import json
import sqlite3 # 用于数据库操作
from typing import Dict, List, Optional, Any, Tuple
import threading
import tmdb_handler
from douban import DoubanApi, clean_character_name_static
# 假设 emby_handler.py, utils.py, logger_setup.py, constants.py 都在同一级别或Python路径中
import emby_handler
import utils # 导入我们上面修改的 utils.py
from utils import LogDBManager
import constants
import logging
import actor_utils
from ai_translator import AITranslator # ✨✨✨ 导入新的AI翻译器 ✨✨✨
from actor_utils import ActorDBManager
# DoubanApi 的导入和可用性检查
logger = logging.getLogger(__name__)
try:
    from douban import DoubanApi # douban.py 现在也使用数据库
    DOUBAN_API_AVAILABLE = True
    logger.debug("DoubanApi 模块已成功导入到 core_processor。")
except ImportError:
    logger.error("错误: douban.py 文件未找到或 DoubanApi 类无法导入 (core_processor)。")
    DOUBAN_API_AVAILABLE = False
    # 创建一个假的 DoubanApi 类，以便在 DoubanApi 不可用时程序仍能运行（但功能受限）
    class DoubanApi:
        def __init__(self, *args, **kwargs): logger.warning("使用的是假的 DoubanApi 实例 (core_processor)。")
        def get_acting(self, *args, **kwargs): return {"error": "DoubanApi not available", "cast": []}
        def close(self): pass
        # 添加静态方法以避免 AttributeError，如果 _translate_actor_field 尝试调用它们
        @staticmethod
        def _get_translation_from_db(*args, **kwargs): return None
        @staticmethod
        def _save_translation_to_db(*args, **kwargs): pass

 
class MediaProcessorAPI:
    # ✨✨✨初始化✨✨✨
    def __init__(self, config: Dict[str, Any]):
        # config 这个参数，是已经从 load_config() 加载好的、一个标准的 Python 字典
        self.config = config
        self.db_path = config.get('db_path')
        if not self.db_path:
            logger.error("MediaProcessorAPI 初始化失败：未在配置中找到 'db_path'。")
            raise ValueError("数据库路径 (db_path) 未在配置中提供给 MediaProcessorAPI。")
        # 初始化我们的数据库管理员
        self.actor_db_manager = ActorDBManager(self.db_path)
        logger.debug("ActorDBManager 实例已在 MediaProcessorAPI 中创建。")
        self.log_db_manager = LogDBManager(self.db_path)

        self.douban_api = None
        if getattr(constants, 'DOUBAN_API_AVAILABLE', False):
            try:
                # --- ✨✨✨ 核心修改区域 START ✨✨✨ ---

                # 1. 从配置中获取冷却时间 (这部分逻辑您可能已经有了)
                douban_cooldown = self.config.get(constants.CONFIG_OPTION_DOUBAN_DEFAULT_COOLDOWN, 2.0)
                
                # 2. 从配置中获取 Cookie，使用我们刚刚在 constants.py 中定义的常量
                douban_cookie = self.config.get(constants.CONFIG_OPTION_DOUBAN_COOKIE, "")
                
                # 3. 添加一个日志，方便调试
                if not douban_cookie:
                    logger.debug(f"配置文件中未找到或未设置 '{constants.CONFIG_OPTION_DOUBAN_COOKIE}'。如果豆瓣API返回'need_login'错误，请在此处配置。")
                else:
                    logger.debug("已从配置中加载豆瓣 Cookie。")

                # 4. 将所有参数传递给 DoubanApi 的构造函数
                self.douban_api = DoubanApi(
                    db_path=self.db_path,
                    cooldown_seconds=douban_cooldown,
                    user_cookie=douban_cookie  # <--- 将 cookie 传进去
                )
                logger.debug("DoubanApi 实例已在 MediaProcessorAPI 中创建。")
                
                # --- ✨✨✨ 核心修改区域 END ✨✨✨ ---

            except Exception as e:
                logger.error(f"MediaProcessorAPI 初始化 DoubanApi 失败: {e}", exc_info=True)
        else:
            logger.warning("DoubanApi 常量指示不可用，将不使用豆瓣功能。")

        # 从 config 字典中安全地获取所有配置
        self.emby_url = self.config.get("emby_server_url")
        self.emby_api_key = self.config.get("emby_api_key")
        self.emby_user_id = self.config.get("emby_user_id")
        self.tmdb_api_key = self.config.get("tmdb_api_key", "")
        self.translator_engines = self.config.get("translator_engines_order", constants.DEFAULT_TRANSLATOR_ENGINES_ORDER)
        self.local_data_path = self.config.get("local_data_path", "").strip()
        self.libraries_to_process = self.config.get("libraries_to_process", [])

        self._stop_event = threading.Event()
        self.processed_items_cache = self._load_processed_log_from_db()

        # ✨✨✨ 关键修复：从 config 字典中获取AI配置 ✨✨✨
        self.ai_translator = None
        self.ai_translation_enabled = self.config.get("ai_translation_enabled", False) 
        
        if self.ai_translation_enabled:
            try:
                self.ai_translator = AITranslator(self.config)
                logger.info("AI翻译器已成功初始化并启用。")
            except Exception as e:
                logger.error(f"AI翻译器初始化失败，将禁用AI翻译功能: {e}")
                self.ai_translation_enabled = False
        else:
            logger.info("AI翻译功能未启用。")

        logger.debug(f"MediaProcessorAPI 初始化完成。Emby URL: {self.emby_url}, UserID: {self.emby_user_id}")
        logger.info(f"  TMDb API Key: {'已配置' if self.tmdb_api_key else '未配置'}")
        logger.debug(f"  本地数据源路径: '{self.local_data_path if self.local_data_path else '未配置'}'")
        logger.debug(f"  将处理的媒体库ID: {self.libraries_to_process if self.libraries_to_process else '未指定特定库'}")
        logger.info(f"  已从数据库加载 {len(self.processed_items_cache)} 个已处理媒体记录到内存缓存。")
        logger.debug(f"  INIT - self.local_data_path: '{self.local_data_path}'")
        logger.debug(f"  INIT - self.tmdb_api_key (len): {len(self.tmdb_api_key) if self.tmdb_api_key else 0}")
        logger.debug(f"  INIT - DOUBAN_API_AVAILABLE (from top level): {DOUBAN_API_AVAILABLE}")
        logger.debug(f"  INIT - self.douban_api is None: {self.douban_api is None}")
        if self.douban_api:
            logger.debug(f"  INIT - self.douban_api type: {type(self.douban_api)}")
    # ✨✨✨占位符✨✨✨
    def check_and_add_to_watchlist(self, item_details: Dict[str, Any]):
        """
        普通模式下，此功能被禁用。定义一个空方法以保证接口统一，避免报错。
        """
        logger.debug("【普通模式】跳过追剧判断（功能禁用）。")
        pass # 什么也不做，直接返回
    # ✨✨✨新处理单个媒体项（电影、剧集或单集）的核心业务逻辑✨✨✨
    def _process_item_api_mode(self, item_details: Dict[str, Any], process_episodes: bool):
        item_id = item_details.get("Id")
        item_name_for_log = item_details.get("Name")
        item_type = item_details.get("Type")

        logger.debug(f"开始处理: '{item_name_for_log}' (类型: {item_type}) ---")
        try:
            # ✨✨✨ 1. 使用 with 语句管理唯一的数据库连接 ✨✨✨
            with self.actor_db_manager.get_db_connection() as conn:
                cursor = conn.cursor()

                # ✨✨✨ 2. 在所有操作开始前，开启一个总事务 ✨✨✨
                cursor.execute("BEGIN TRANSACTION;")
                logger.debug(f"API 模式 (ItemID: {item_id}) 的数据库事务已开启。")

                try:
            
                    # a. 获取并处理当前项目的演员表
                    current_emby_cast_raw = item_details.get("People", [])
                    original_emby_cast_count = len(current_emby_cast_raw)
                    
                    final_cast_for_item = self._process_cast_list(
                        current_emby_cast_raw, 
                        item_details,
                        cursor  # <--- 把 cursor 加在这里
                    )

                    # ✨✨✨ 统计日志块 ✨✨✨
                    # ==================================================================
                    final_actor_count = len(final_cast_for_item)
                    logger.info(f"✨✨✨处理统计 '{item_name_for_log}'✨✨✨")
                    logger.info(f"  - 原有演员: {original_emby_cast_count} 位")
                    
                    count_diff = final_actor_count - original_emby_cast_count
                    if count_diff != 0:
                        change_str = f"  - 新增 {count_diff}" if count_diff > 0 else f"减少 {abs(count_diff)}"
                        logger.info(f"  - 数量变化: {change_str} 位")

                    logger.info(f"  - 最终演员: {final_actor_count} 位")
                    # ✨✨✨ 日志块结束 ✨✨✨
                    
                    # b. 评分
                    # ✨ 在调用评分函数前，先判断类型
                    processing_score = 10.0 # 默认给一个满分，如果不是电影/剧集则不改变
                    if item_type in ["Movie", "Series"]:
                        logger.debug(f"正在为 {item_type} '{item_name_for_log}' 进行质量评估...")
                        
                        # ✨✨✨ 2. 正确的动画片判断 ✨✨✨
                        genres = item_details.get("Genres", [])
                        animation_tags = {"Animation", "动画", "动漫"}
                        genres_set = set(genres)
                        is_animation = not animation_tags.isdisjoint(genres_set)
                        
                        if is_animation:
                            logger.debug(f"检测到媒体 '{item_name_for_log}' 为动画片，评分时将跳过数量惩罚。")

                        # ✨✨✨ 3. 正确地调用公共评分函数 ✨✨✨
                        processing_score = actor_utils.evaluate_cast_processing_quality(
                            final_cast=final_cast_for_item, 
                            original_cast_count=original_emby_cast_count,
                            expected_final_count=len(final_cast_for_item), # 传入截断后的数量
                            is_animation=is_animation # 把判断结果传进去
                        )

                    # c. 持久化当前项目的演员表 (两步更新)
                    logger.debug("开始前置步骤：检查并更新被翻译的演员名字...")
                    original_names_map = {p.get("Id"): p.get("Name") for p in current_emby_cast_raw if p.get("Id")}
                    for actor in final_cast_for_item:
                        if self.is_stop_requested(): raise InterruptedError("任务中止")
                        actor_id = actor.get("EmbyPersonId")
                        new_name = actor.get("Name")
                        original_name = original_names_map.get(actor_id)
                        if actor_id and new_name and original_name and new_name != original_name:
                            emby_handler.update_person_details(actor_id, {"Name": new_name}, self.emby_url, self.emby_api_key, self.emby_user_id)
                    
                    cast_for_handler = [{"name": a.get("Name"), "character": a.get("Role"), "emby_person_id": a.get("EmbyPersonId")} for a in final_cast_for_item]
                    update_success = emby_handler.update_emby_item_cast(item_id, cast_for_handler, self.emby_url, self.emby_api_key, self.emby_user_id)
                    if not update_success:
                        raise RuntimeError(f"普通模式更新项目 '{item_name_for_log}' 演员列表失败")

                    # d. 新增逻辑：如果当前是剧集，则将这份演员表注入所有“季”和“分集”
                    if item_type == "Series":
                        logger.debug(f"【普通模式-批量注入】准备将处理好的演员表注入到 '{item_name_for_log}' 的所有子项中...")
                        children = emby_handler.get_series_children(item_id, self.emby_url, self.emby_api_key, self.emby_user_id, item_name_for_log)
                        
                        if children:
                            # <<< --- 核心修改：新增季演员表注入逻辑 --- >>>
                            seasons = [child for child in children if child.get("Type") == "Season"]
                            if seasons:
                                total_seasons = len(seasons)
                                logger.debug(f"【普通模式-批量注入】找到 {total_seasons} 个季，将为其注入演员表...")
                                for i, season in enumerate(seasons):
                                    if self.is_stop_requested(): raise InterruptedError("任务中止")
                                    season_id = season.get("Id")
                                    season_name = season.get("Name")
                                    logger.debug(f"  ({i+1}/{total_seasons}) 正在为季 '{season_name}' 更新演员表...")
                                    
                                    emby_handler.update_emby_item_cast(season_id, cast_for_handler, self.emby_url, self.emby_api_key, self.emby_user_id)
                                    
                                    time.sleep(float(self.config.get("delay_between_items_sec", 0.2)))
                            # <<< --- 核心修改结束 --- >>>

                            if process_episodes:
                                episodes = [child for child in children if child.get("Type") == "Episode"]
                                if episodes:
                                    total_episodes = len(episodes)
                                    logger.debug(f"【普通模式-批量注入】找到 {total_episodes} 个分集需要更新。")
                                    logger.info(f"  - 正在为分集注入演员表...")

                                    for i, episode in enumerate(episodes):
                                        if self.is_stop_requested(): raise InterruptedError("任务中止")
                                        episode_id = episode.get("Id")
                                        episode_name = episode.get("Name")
                                        logger.debug(f"  ({i+1}/{total_episodes}) 正在为分集 '{episode_name}' 更新演员表...")
                                        
                                        emby_handler.update_emby_item_cast(episode_id, cast_for_handler, self.emby_url, self.emby_api_key, self.emby_user_id)
                                        
                                        time.sleep(float(self.config.get("delay_between_items_sec", 0.2)))
                    
                    # ★★★ 在这里，记录主项目日志之前，添加刷新操作 ★★★
                    logger.debug(f"所有演员信息更新完成，准备为项目 '{item_name_for_log}' 触发元数据刷新...")
                    refresh_success = emby_handler.refresh_emby_item_metadata(
                        item_emby_id=item_id,
                        emby_server_url=self.emby_url,
                        emby_api_key=self.emby_api_key,
                        replace_all_metadata_param=False, # <-- 普通模式使用“补充缺失”模式
                        item_name_for_log=item_name_for_log
                    )
                    logger.info(f"✨✨✨处理完成 '{item_name_for_log}'✨✨✨")
                    conn.commit()

                except InterruptedError:
                    logger.info(f"处理 '{item_name_for_log}' 的过程中被用户中止。")
                    logger.warning("正在回滚数据库事务...")
                    conn.rollback()
                    raise # 重新抛出，让上层知道任务被中止
                except Exception as inner_e:
                    logger.error(f"在事务处理中发生错误 for media '{item_name_for_log}': {inner_e}", exc_info=True)
                    logger.warning("正在回滚数据库事务...")
                    conn.rollback()
                    raise # 重新抛出，让上层知道处理失败

        except Exception as outer_e:
            logger.error(f"处理 '{item_name_for_log}' 时发生严重错误（如数据库连接失败）: {outer_e}", exc_info=True)
            # 在这里，我们不能写入数据库日志，因为连接可能已经失败
            # 记录到应用日志中即可
    # ✨✨✨获取数据库连接的辅助方法✨✨✨
    def _get_db_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row # 方便按列名访问
        return conn
    # ✨✨✨设置停止信号，用于在多线程环境中优雅地中止长时间运行的任务✨✨✨
    def signal_stop(self):
        logger.info("MediaProcessorAPI 收到停止信号。")
        self._stop_event.set()
    # ✨✨✨清除停止信号，以便开始新的任务✨✨✨
    def clear_stop_signal(self):
        self._stop_event.clear()
        logger.debug("MediaProcessorAPI 停止信号已清除。")
    def get_stop_event(self) -> threading.Event:
        """返回内部的停止事件对象，以便传递给其他函数。"""
        return self._stop_event
    # ✨✨✨检查是否已请求停止当前任务✨✨✨
    def is_stop_requested(self) -> bool:
        return self._stop_event.is_set()
    # ✨✨✨从数据库加载所有已处理过的项目ID到内存缓存中，以提高启动速度和避免重复处理✨✨✨
    def _load_processed_log_from_db(self) -> Dict[str, str]:
        # 这一块的所有内容都需要缩进！
        log_dict = {}
        try:
            # self 前面有4个空格的缩进
            conn = self._get_db_connection()
            cursor = conn.cursor()
            # 同时查询 item_id 和 item_name
            cursor.execute("SELECT item_id, item_name FROM processed_log")
            rows = cursor.fetchall()
            for row in rows:
                # 将 ID 和 名称 存入字典
                if row['item_id'] and row['item_name']:
                    log_dict[row['item_id']] = row['item_name']
            conn.close()
        except Exception as e:
            logger.error(f"从数据库读取已处理记录失败: {e}", exc_info=True)
        
        # return 前面也有4个空格的缩进
        return log_dict
    # ✨✨✨清除数据库中的所有已处理记录以及内存中的缓存✨✨✨
    def clear_processed_log(self):
        """清除数据库中的已处理记录和内存缓存。"""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM processed_log")
            conn.commit()
            conn.close()
            self.processed_items_cache.clear()
            logger.info("数据库和内存中的已处理记录已清除。")
        except Exception as e:
            logger.error(f"清除数据库已处理记录失败: {e}", exc_info=True)
    # ✨✨✨处理单个媒体项目演员列表的核心方法✨✨✨
    def _process_cast_list(self, current_emby_cast_people: List[Dict[str, Any]], media_info: Dict[str, Any], cursor: sqlite3.Cursor) -> List[Dict[str, Any]]:
        media_name_for_log = media_info.get("Name", "未知媒体")
        media_id_for_log = media_info.get("Id", "未知ID")
        media_type_for_log = media_info.get("Type")
        logger.info(f"开始处理媒体 '{media_name_for_log}' (ID: {media_id_for_log}) 的演员列表，遵循 'enrich-only' 模式。")



        # ======================================================================
        # 步骤 1: 初始化 Emby 演员基准列表
        # ======================================================================
        logger.info(f"步骤 1: 初始化 Emby 演员基准列表 ({len(current_emby_cast_people)} 位)...")
        final_cast_list: List[Dict[str, Any]] = []
        for person_emby in current_emby_cast_people:
            if self.is_stop_requested(): break
            emby_pid = str(person_emby.get("Id", "")).strip()
            emby_name = str(person_emby.get("Name", "")).strip()
            if not emby_pid or not emby_name:
                continue

            provider_ids = person_emby.get("ProviderIds", {})
            actor_internal_format = {
                "Name": emby_name,
                "OriginalName": person_emby.get("OriginalName", emby_name),
                "Role": str(person_emby.get("Role", "")).strip(),
                "Type": "Actor",
                "EmbyPersonId": emby_pid,
                "TmdbPersonId": str(provider_ids.get("Tmdb", "")).strip() or None,
                "DoubanCelebrityId": str(provider_ids.get("Douban", "")).strip() or None,
                "ImdbId": str(provider_ids.get("Imdb", "")).strip() or None,
                "ProviderIds": provider_ids.copy(),
                "Order": person_emby.get("Order"),
                "_source_comment": "from_emby_initial"
            }
            final_cast_list.append(actor_internal_format)
            # 使用 Emby 的原始数据更新映射表
            self.actor_db_manager.upsert_person(
                cursor,
                {  # <--- 注意这里，创建了一个字典
                    "emby_id": actor_internal_format["EmbyPersonId"],
                    "name": actor_internal_format["Name"],  # 函数内部用的是 'name'
                    "tmdb_id": actor_internal_format["TmdbPersonId"],
                    "douban_id": actor_internal_format["DoubanCelebrityId"],
                    "imdb_id": actor_internal_format["ImdbId"]
                }
            )

        logger.info(f"步骤 1: 基准列表创建完成，包含 {len(final_cast_list)} 位演员。")
        if self.is_stop_requested():
            return final_cast_list

        # ======================================================================
        # 步骤 2: 从豆瓣获取数据并与基准列表比对 (丰富现有演员)
        # ======================================================================
        logger.info("步骤 2: 获取豆瓣演员并与基准列表比对...")
        formatted_douban_candidates = []
        if media_type_for_log in ["Movie", "Series"]:
            douban_api_actors_raw = actor_utils.find_douban_cast(self.douban_api, media_info)
            formatted_douban_candidates = actor_utils.format_douban_cast(douban_api_actors_raw)
            logger.info(f"从豆瓣 API 格式化后得到 {len(formatted_douban_candidates)} 位候选演员。")
        else:
            logger.info(f"步骤 2: 跳过获取豆瓣演员 (因为类型是 {media_type_for_log})。")

        unmatched_douban_candidates: List[Dict[str, Any]] = []
        if formatted_douban_candidates:
            matched_douban_indices = set()
            for i, douban_candidate in enumerate(formatted_douban_candidates):
                if self.is_stop_requested(): break
                
                match_found = False
                for emby_actor_to_update in final_cast_list:
                    is_match, match_reason = False, ""
                    dc_douban_id = douban_candidate.get("DoubanCelebrityId")
                    if dc_douban_id and dc_douban_id == emby_actor_to_update.get("DoubanCelebrityId"):
                        is_match, match_reason = True, f"Douban ID ({dc_douban_id})"
                    
                    if not is_match:
                        # --- 引擎1: 简单直接的精确匹配 (高优先级) ---
                        dc_name_lower = str(douban_candidate.get("Name") or "").lower().strip()
                        dc_orig_name_lower = str(douban_candidate.get("OriginalName") or "").lower().strip()
                        emby_name_lower = str(emby_actor_to_update.get("Name") or "").lower().strip()
                        emby_orig_name_lower = str(emby_actor_to_update.get("OriginalName") or "").lower().strip()

                        if dc_name_lower and (dc_name_lower == emby_name_lower or dc_name_lower == emby_orig_name_lower):
                            is_match, match_reason = True, f"精确匹配 (豆瓣中文名)"
                        elif dc_orig_name_lower and (dc_orig_name_lower == emby_name_lower or dc_orig_name_lower == emby_orig_name_lower):
                            is_match, match_reason = True, f"精确匹配 (豆瓣外文名)"


                    if is_match:
                        logger.info(f"  匹配成功: ...")
                        
                        # 更新内存中的对象
                        if dc_douban_id and not emby_actor_to_update.get("DoubanCelebrityId"):
                            emby_actor_to_update["DoubanCelebrityId"] = dc_douban_id
                            emby_actor_to_update["ProviderIds"]["Douban"] = dc_douban_id
                            logger.info(f"    -> 已为该演员补充 Douban ID: {dc_douban_id}")
                        
                        # ... 更新角色 ...

                        # ✨✨✨ 核心修正：调用 upsert 时，传递所有已知的ID ✨✨✨
                        self.actor_db_manager.upsert_person(
                            cursor,
                            {
                                "name": emby_actor_to_update.get("Name"),
                                "emby_id": emby_actor_to_update.get("EmbyPersonId"),
                                "tmdb_id": emby_actor_to_update.get("TmdbPersonId"),
                                "imdb_id": emby_actor_to_update.get("ImdbId"),
                                "douban_id": emby_actor_to_update.get("DoubanCelebrityId") # 包含新补充的ID
                            }
                        )
                        
                        matched_douban_indices.add(i)
                        match_found = True
                        break
                
                if not match_found:
                    unmatched_douban_candidates.append(douban_candidate)
        
        logger.info(f"步骤 2: 完成。{len(matched_douban_indices) if formatted_douban_candidates else 0} 位豆瓣演员已匹配，{len(unmatched_douban_candidates)} 位溢出。")
        if self.is_stop_requested():
            return final_cast_list

        # ======================================================================
        # 步骤 3: 条件化处理流程 (核心逻辑分叉点)
        # ======================================================================
        limit = self.config.get(constants.CONFIG_OPTION_MAX_ACTORS_TO_PROCESS, 30)
        try:
            limit = int(limit)
            if limit <= 0: limit = 30
        except (ValueError, TypeError):
            limit = 30
        
        current_actor_count = len(final_cast_list)

        if current_actor_count >= limit:
            logger.info(f"当前演员数 ({current_actor_count}) 已达上限 ({limit})，将跳过所有新增演员的流程。")
            if unmatched_douban_candidates:
                discarded_names = [d.get('Name') for d in unmatched_douban_candidates]
                logger.info(f"--- 因此，将丢弃 {len(discarded_names)} 位未能匹配的豆瓣演员: {', '.join(discarded_names[:5])}{'...' if len(discarded_names) > 5 else ''} ---")
        else:
            logger.info(f"当前演员数 ({current_actor_count}) 低于上限 ({limit})，进入补充模式，继续处理 {len(unmatched_douban_candidates)} 位溢出的豆瓣演员。")
            
            if current_actor_count >= limit:
                logger.info(f"当前演员数 ({current_actor_count}) 已达上限 ({limit})，将跳过所有新增演员的流程。")
                if unmatched_douban_candidates:
                    # 即使达到上限，也打印一下丢弃日志
                    discarded_names = [d.get('Name') for d in unmatched_douban_candidates]
                    logger.info(f"--- 因此，将丢弃 {len(discarded_names)} 位未能匹配的豆瓣演员: {', '.join(discarded_names[:5])}{'...' if len(discarded_names) > 5 else ''} ---")
            else:
                # ✨✨✨ 精准手术在这里 ✨✨✨
                # 我们不再进行任何TMDb API的交叉匹配，直接丢弃所有未能匹配的豆瓣演员。
                # 所有新增演员的逻辑，都将依赖于后台的详情补充任务和下一次处理。
                logger.info(f"当前演员数 ({current_actor_count}) 低于上限 ({limit})，等演员映射表数据更充实时，请重新进行处理。")
                if unmatched_douban_candidates:
                    discarded_names = [d.get('Name') for d in unmatched_douban_candidates]
                    logger.info(f"--- 将丢弃 {len(discarded_names)} 位本地映射表无法直接匹配的豆瓣演员: {', '.join(discarded_names[:5])}{'...' if len(discarded_names) > 5 else ''} ---")

        logger.info("步骤 3: 条件化处理完成。")
        if self.is_stop_requested():
            return final_cast_list
        
        # ======================================================================
        # 步骤 4: 最终截断
        # ======================================================================
        original_count = len(final_cast_list)
        if original_count > limit:
            logger.info(f"演员列表总数 ({original_count}) 超过上限 ({limit})，将在翻译前进行截断。")
            final_cast_list.sort(key=lambda x: x.get('Order') if x.get('Order') is not None and x.get('Order') >= 0 else 999)
            final_cast_list = final_cast_list[:limit]
            logger.info(f"截断后，剩余 {len(final_cast_list)} 位演员进入最终处理。")

        # ======================================================================
        # 步骤 5: 对最终演员表进行翻译和格式化
        # ======================================================================
        logger.info(f"步骤 5: 对最终 {len(final_cast_list)} 位演员进行翻译和格式化...")
        
        ai_translation_succeeded = False

        if self.ai_translation_enabled and self.ai_translator:
            logger.info("AI翻译已启用，优先尝试批量翻译模式。")
            texts_to_translate = set()
            translation_cache = {} # 用于存储从数据库或API获取的翻译结果

            # 1. 收集所有需要翻译的文本，并优先使用数据库缓存
            for actor in final_cast_list:
                for field_key in ["Name", "Role"]:
                    original_text = actor.get(field_key)
                    if field_key == 'Role':
                        original_text = utils.clean_character_name_static(original_text)
                    
                    if not original_text or not original_text.strip() or utils.contains_chinese(original_text):
                        continue

                    cached_entry = DoubanApi._get_translation_from_db(original_text, cursor=cursor)
                    if cached_entry and cached_entry.get("translated_text"):
                        translation_cache[original_text] = cached_entry.get("translated_text")
                    else:
                        texts_to_translate.add(original_text)
            
            # 2. 如果有需要翻译的文本，则调用批量API
            if texts_to_translate:
                logger.info(f"共收集到 {len(texts_to_translate)} 个独立词条需要通过AI翻译。")
                try:
                    translation_map = self.ai_translator.batch_translate(list(texts_to_translate))
                    
                    if translation_map:
                        logger.info(f"AI批量翻译成功，返回 {len(translation_map)} 个结果。")
                        translation_cache.update(translation_map)
                        
                        # 将新翻译的结果存入数据库缓存
                        for original, translated in translation_map.items():
                            DoubanApi._save_translation_to_db(original, translated, self.ai_translator.provider, cursor=cursor)
                        
                        ai_translation_succeeded = True
                    else:
                        logger.warning("AI批量翻译调用成功，但未返回任何翻译结果。可能是API内部错误（如余额不足）。将降级到传统翻译引擎。")

                except Exception as e:
                    logger.error(f"调用AI批量翻译时发生严重错误: {e}。将降级到传统翻译引擎。", exc_info=True)
            else:
                logger.info("所有词条均在缓存中找到，无需AI翻译。")
                ai_translation_succeeded = True

            # 3. 如果AI成功（无论通过API还是缓存），则回填结果
            if ai_translation_succeeded:
                for actor_data in final_cast_list:
                    # 更新名字
                    original_name = actor_data.get("Name")
                    if original_name in translation_cache:
                        actor_data["Name"] = translation_cache[original_name]
                    
                    # 更新角色
                    original_role = utils.clean_character_name_static(actor_data.get("Role"))
                    if original_role in translation_cache:
                        actor_data["Role"] = translation_cache[original_role]
                    else:
                        actor_data["Role"] = original_role

        # ★★★ 降级逻辑 ★★★
        if not ai_translation_succeeded:
            if self.config.get("ai_translation_enabled", False):
                logger.info("AI翻译失败，正在启动降级程序，使用传统翻译引擎...")
            else:
                logger.info("AI翻译未启用，使用传统翻译引擎（如果配置了）。")
            
            # 使用健壮的逐个翻译逻辑作为回退
            for actor_data in final_cast_list:
                if self.is_stop_requested(): break
                
                current_name = actor_data.get("Name")
                actor_data["Name"] = actor_utils.translate_actor_field(current_name, "演员名", current_name, db_cursor_for_cache=cursor)

                role_cleaned = utils.clean_character_name_static(actor_data.get("Role"))
                actor_data["Role"] = actor_utils.translate_actor_field(role_cleaned, "角色名", actor_data.get("Name"), db_cursor_for_cache=cursor)

        # 翻译完成后，进行统一的格式化处理
        is_animation = "Animation" in media_info.get("Genres", []) or "动画" in media_info.get("Genres", [])
        for actor_data in final_cast_list:
            final_role = actor_data.get("Role", "")

            # 移除中文角色名中的所有空格
            if final_role and utils.contains_chinese(final_role):
                final_role = final_role.replace(" ", "").replace("　", "")
            
            if is_animation:
                final_role = f"{final_role} (配音)" if final_role and not final_role.endswith("(配音)") else "配音"
            elif not final_role:
                final_role = "演员"
            
            if final_role != actor_data.get("Role"):
                logger.debug(f"  角色名格式化: '{actor_data.get('Role')}' -> '{final_role}' (演员: {actor_data.get('Name')})")
                actor_data["Role"] = final_role

        logger.info(f"演员列表最终处理完成，返回 {len(final_cast_list)} 位演员。")
        return final_cast_list
    # ✨✨✨处理单个媒体项目（电影或剧集）的入口方法✨✨✨
    def process_single_item(self, emby_item_id: str, force_reprocess_this_item: bool = False, process_episodes: bool = True) -> bool:
        if self.is_stop_requested():
            return False

        if not force_reprocess_this_item and emby_item_id in self.processed_items_cache:
            logger.info(f"媒体 '{self.processed_items_cache.get(emby_item_id, emby_item_id)}' 已处理过，跳过。")
            return True

        try:
            item_details = emby_handler.get_emby_item_details(emby_item_id, self.emby_url, self.emby_api_key, self.emby_user_id)
            if not item_details:
                self.save_to_failed_log(emby_item_id, f"未知项目(ID:{emby_item_id})", "无法获取Emby项目详情")
                return False
        except Exception as e:
            self.save_to_failed_log(emby_item_id, f"未知项目(ID:{emby_item_id})", f"获取Emby详情异常: {e}")
            return False

        item_name_for_log = item_details.get("Name", f"ID:{emby_item_id}")
        
        try:
            # ★★★ 核心：直接调用我们新的、统一的流程函数 ★★★
            # 并将 process_episodes 参数传递下去
            self._process_item_api_mode(item_details, process_episodes)
            
            return True
        except InterruptedError:
            logger.info(f"处理 '{item_name_for_log}' 的过程中被用户中止。")
            return False
        except Exception as e:
            logger.error(f"处理 '{item_name_for_log}' 时发生严重错误: {e}", exc_info=True)
            self.save_to_failed_log(emby_item_id, item_name_for_log, f"核心处理异常: {str(e)}", item_details.get("Type"))
            return False
    # ✨✨✨使用手动编辑的演员列表来处理单个媒体项目✨✨✨    
    def process_item_with_manual_cast(self, item_id: str, manual_cast_list: List[Dict[str, Any]]) -> bool:
        """
        使用手动编辑的演员列表来处理单个媒体项目。
        这个函数是为手动编辑 API 设计的，它会执行完整的“两步更新+锁定刷新”流程。
        """
        logger.info(f"开始使用手动编辑的演员列表处理 Item ID: {item_id}")
        
        # 1. 获取原始 Emby 详情，用于对比名字变更
        try:
            item_details = emby_handler.get_emby_item_details(item_id, self.emby_url, self.emby_api_key, self.emby_user_id)
            if not item_details:
                logger.error(f"手动处理失败：无法获取项目 {item_id} 的详情。")
                return False
            current_emby_cast_raw = item_details.get("People", [])
            item_name_for_log = item_details.get("Name", f"ID:{item_id}")
            item_type_for_log = item_details.get("Type", "Unknown")
        except Exception as e:
            logger.error(f"手动处理失败：获取项目 {item_id} 详情时异常: {e}")
            return False

        # 2. 前置更新：更新被手动修改了名字的 Person 条目
        logger.info("手动处理：开始前置翻译演员名字...")
        original_names_map = {p.get("Id"): p.get("Name") for p in current_emby_cast_raw if p.get("Id")}
        for actor in manual_cast_list:
            actor_id = actor.get("emby_person_id")
            new_name = actor.get("name")
            original_name = original_names_map.get(actor_id)
            if actor_id and new_name and original_name and new_name != original_name:
                logger.info(f"手动处理：检测到名字变更 '{original_name}' -> '{new_name}' (ID: {actor_id})")
                emby_handler.update_person_details(
                    person_id=actor_id,
                    new_data={"Name": new_name},
                    emby_server_url=self.emby_url,
                    emby_api_key=self.emby_api_key,
                    user_id=self.emby_user_id
                )
        logger.info("手动处理：演员名字前置翻译完成。")

        # 3. 最终更新：将手动编辑的列表更新到媒体
        logger.info(f"手动处理：准备将 {len(manual_cast_list)} 位演员更新到 Emby...")
        update_success = emby_handler.update_emby_item_cast(
            item_id=item_id,
            new_cast_list_for_handler=manual_cast_list,
            emby_server_url=self.emby_url,
            emby_api_key=self.emby_api_key,
            user_id=self.emby_user_id
        )

        if not update_success:
            logger.error(f"手动处理失败：更新 Emby 项目 {item_id} 演员信息时失败。")
            return False

        # # 4. 收尾工作：刷新EMBY
        # logger.info(f"手动处理：演员更新成功，准备锁定并刷新...")
        # if self.config.get("lock_cast_before_refresh", True):
        #     emby_handler.lock_emby_item_field(item_id, "Cast", self.emby_url, self.emby_api_key, self.emby_user_id)
        #     emby_handler.refresh_emby_item_metadata(item_id, self.emby_url, self.emby_api_key, recursive=(item_type_for_log == "Series"))
        
        logger.info(f"手动处理 Item ID: {item_id} ('{item_name_for_log}') 完成。")
        return True
    # ✨✨✨将从 TMDb API 获取的演员数据格式化为 Emby Handler 或内部处理所需的标准字典格式✨✨✨
    def _format_tmdb_person_for_emby_handler(self, tmdb_person_data: Dict[str, Any],
                                             role_from_source: Optional[str] = None
                                             ) -> Dict[str, Any]:
        """
        将从 TMDb API 获取的演员数据格式化。
        主要名字直接使用 TMDb 返回的 name。
        """
        tmdb_id_str = str(tmdb_person_data.get("id")) if tmdb_person_data.get("id") else None
        final_role = utils.clean_character_name_static(role_from_source) if role_from_source and role_from_source.strip() else "演员"

        name_from_tmdb = tmdb_person_data.get("name") # 直接使用 TMDb 的名字
        # original_name 可以是 TMDb 的 name (如果它是外文)，或者也用 name_from_tmdb
        # 如果 tmdb_person_data 中有 'original_name' 字段且不同于 'name'，也可以考虑使用
        original_name_to_use = tmdb_person_data.get("original_name", name_from_tmdb)


        actor_entry = {
            "Name": name_from_tmdb, # <--- 使用 TMDb 的名字
            "OriginalName": original_name_to_use,
            "Role": final_role,
            "Type": "Actor", # Emby 需要这个
            "ProviderIds": {},
            "EmbyPersonId": None, # 新增演员，初始没有 Emby Person ID
            "TmdbPersonId": tmdb_id_str, # 存储 TMDb Person ID
            "DoubanCelebrityId": None, # 初始设为 None，如果源数据有，后面会填充
            "ProfileImagePathTMDb": tmdb_person_data.get("profile_path"),
            "_source": "tmdb_added_or_enhanced" # 标记来源
        }
        if tmdb_id_str:
            actor_entry["ProviderIds"]["Tmdb"] = tmdb_id_str

        external_ids = tmdb_person_data.get("external_ids", {}) # 来自 get_person_details_tmdb
        tmdb_imdb_id = external_ids.get("imdb_id")
        if tmdb_imdb_id:
            actor_entry["ProviderIds"]["Imdb"] = tmdb_imdb_id
        
        # 如果 tmdb_person_data 中有 translations，可以考虑提取中文名作为 Name (如果 Name 当前是外文)
        # 例如:
        # translations = tmdb_person_data.get("translations", {}).get("translations", [])
        # for trans in translations:
        #     if trans.get("iso_639_1") == "zh" and trans.get("data", {}).get("name"):
        #         actor_entry["Name"] = trans["data"]["name"]
        #         logger.debug(f"  使用TMDb的中文翻译 '{actor_entry['Name']}' 替换/作为演员名。")
        #         break # 通常取第一个中文翻译即可

        return actor_entry
    # ✨✨✨处理配置文件中指定的所有媒体库的入口方法✨✨✨
    def process_full_library(self, update_status_callback: Optional[callable] = None, force_reprocess_all: bool = False, process_episodes: bool = True):
        self.clear_stop_signal()
        logger.debug("process_full_library: 方法开始执行。")
        logger.debug(f"  force_reprocess_all: {force_reprocess_all}, process_episodes: {process_episodes}")

        if force_reprocess_all:
            logger.info("用户请求强制重处理所有媒体项，将清除数据库中的已处理记录。")
            self.clear_processed_log()

        if not all([self.emby_url, self.emby_api_key, self.emby_user_id]):
            logger.error("Emby配置不完整，无法处理整个媒体库。")
            if update_status_callback:
                update_status_callback(-1, "Emby配置不完整")
            return

        current_libs_to_process = self.libraries_to_process
        if not current_libs_to_process:
            logger.warning("配置中要处理的媒体库ID列表为空，无需处理。")
            if update_status_callback:
                update_status_callback(100, "未在配置中指定要处理的媒体库。")
            return

        logger.info(f"开始全量处理选定的Emby媒体库 (ID(s): {current_libs_to_process})...")
        
        movies = emby_handler.get_emby_library_items(self.emby_url, self.emby_api_key, "Movie", self.emby_user_id, library_ids=current_libs_to_process) or []
        if self.is_stop_requested(): return

        series_list = emby_handler.get_emby_library_items(self.emby_url, self.emby_api_key, "Series", self.emby_user_id, library_ids=current_libs_to_process) or []
        if self.is_stop_requested(): return

        all_items = movies + series_list
        total_items = len(all_items)

        if total_items == 0:
            logger.info("从选定的媒体库中未获取到任何电影或剧集项目，处理结束。")
            if update_status_callback:
                update_status_callback(100, "未在选定库中找到项目。")
            return

        logger.info(f"总共获取到 {len(movies)} 部电影和 {len(series_list)} 部剧集，共 {total_items} 个项目待处理。")

        for i, item in enumerate(all_items):
            if self.is_stop_requested():
                logger.info("全量媒体库处理在项目迭代中被用户中断。")
                break

            item_id = item.get('Id')
            if not item_id:
                logger.warning(f"条目缺少ID，跳过: {item.get('Name')}")
                continue

            progress_percent = int(((i + 1) / total_items) * 100)
            message = f"正在处理 ({i+1}/{total_items}): {item.get('Name')}"
            logger.info(f"--- {message} ---")
            if update_status_callback:
                update_status_callback(progress_percent, message)

            # ✨ 只保留这一个干净的调用 ✨
            self.process_single_item(
                item_id, 
                force_reprocess_this_item=force_reprocess_all,
                process_episodes=process_episodes
            )

            delay = float(self.config.get("delay_between_items_sec", 0.5))
            if delay > 0 and i < total_items - 1:
                time.sleep(delay)

        if not self.is_stop_requested():
            logger.info("全量处理Emby媒体库结束。")
            if update_status_callback:
                update_status_callback(100, "全量处理完成。")
    # ✨✨✨关闭 MediaProcessorAPI 实例，释放其占用的所有资源（如数据库连接、API会话等）✨✨✨
    def close(self):
        """关闭 MediaProcessorAPI 实例，例如关闭数据库连接池或释放其他资源。"""
        if self.douban_api and hasattr(self.douban_api, 'close'):
            logger.debug("正在关闭 MediaProcessorAPI 中的 DoubanApi session...")
            self.douban_api.close()
        # 如果有其他需要关闭的资源，例如数据库连接池（如果使用的话），在这里关闭
        logger.debug("MediaProcessorAPI close 方法执行完毕。")
    # ✨✨✨使用从网页提取的新演员列表来“补充”当前演员列表✨✨✨
    def enrich_cast_list(self, current_cast: List[Dict[str, Any]], new_cast_from_web: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        使用从网页提取的新列表来补充（Enrich）当前演员列表。
        采用反向翻译匹配：将当前演员的中文名翻译成英文，再去匹配网页提取的英文列表。
        """
        logger.info(f"开始“仅补充”模式（反向翻译匹配）：使用 {len(new_cast_from_web)} 位新演员信息来更新 {len(current_cast)} 位当前演员。")
        
        enriched_cast = [dict(actor) for actor in current_cast]
        used_new_actor_indices = set()
        
        # 我们需要一个数据库连接来调用翻译缓存和在线翻译
        conn = self._get_db_connection()
        cursor = conn.cursor()

        try:
            for i, current_actor in enumerate(enriched_cast):
                current_name_zh = current_actor.get('name', '').strip()
                if not current_name_zh or not utils.contains_chinese(current_name_zh):
                    # 如果当前演员名不是中文，就直接进行常规匹配
                    logger.debug(f"当前演员 '{current_name_zh}' 非中文，使用直接匹配。")
                    # (这里可以保留之前的直接匹配逻辑，为简化，我们先专注解决中文名问题)
                    pass
                
                # --- 核心：反向翻译匹配 ---
                # 将当前演员的中文名翻译成英文
                # 注意：_translate_actor_field 内部会自动处理缓存
                translated_name_en = actor_utils.translate_actor_field(
                    text=current_name_zh,
                    field_name="演员名(用于匹配)",
                    actor_name_for_log=current_name_zh,
                    db_cursor_for_cache=cursor
                )
                
                # 如果翻译结果和原文一样（说明翻译失败或已经是英文），则跳过这个演员
                if translated_name_en == current_name_zh:
                    logger.debug(f"演员 '{current_name_zh}' 翻译失败或无需翻译，跳过反向匹配。")
                    continue

                logger.info(f"尝试为 '{current_name_zh}' (翻译为: '{translated_name_en}') 寻找匹配...")

                # 在新列表中寻找能与翻译后的英文名匹配的项
                for j, new_actor in enumerate(new_cast_from_web):
                    if j in used_new_actor_indices:
                        continue

                    new_name_en = new_actor.get('name', '').strip()
                    if not new_name_en:
                        continue

                    # 进行不区分大小写的匹配
                    if translated_name_en.lower() == new_name_en.lower():
                        logger.info(f"匹配成功: '{current_name_zh}' <=> '{new_name_en}' (通过翻译)")
                        
                        new_role = new_actor.get('role')
                        if new_role:
                            logger.info(f"  -> 角色名更新: '{current_actor.get('role')}' -> '{new_role}'")
                            enriched_cast[i]['role'] = new_role
                        
                        enriched_cast[i]['matchStatus'] = '已更新(翻译匹配)'
                        used_new_actor_indices.add(j)
                        break # 找到匹配，处理下一个当前演员

            # 提交可能在翻译过程中产生的数据库缓存更新
            conn.commit()

        except Exception as e:
            logger.error(f"在 enrich_cast_list 中发生错误: {e}", exc_info=True)
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

        unmatched_count = len(new_cast_from_web) - len(used_new_actor_indices)
        if unmatched_count > 0:
            logger.info(f"{unmatched_count} 位从网页提取的演员未能匹配任何现有演员，已被丢弃。")

        logger.info(f"“仅补充”模式完成，返回 {len(enriched_cast)} 位演员。")
        return enriched_cast
    # ✨✨✨一键翻译演员列表✨✨✨
    def translate_cast_list(self, cast_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        【批量优化版】翻译演员列表中的演员名和角色名，不执行任何其他操作。
        """
        if not cast_list:
            return []

        logger.info(f"一键翻译：开始批量处理 {len(cast_list)} 位演员的姓名和角色。")
        translated_cast = [dict(actor) for actor in cast_list]
        
        ai_translation_succeeded = False

        # 优先尝试AI批量翻译
        if self.ai_translator and self.config.get("ai_translation_enabled", False):
            texts_to_translate = set()
            
            # 1. 收集所有需要翻译的文本
            for actor in translated_cast:
                for field_key in ['name', 'role']:
                    text = actor.get(field_key, '').strip()
                    if text and not utils.contains_chinese(text):
                        texts_to_translate.add(text)
            
            # 2. 如果有需要翻译的文本，则调用批量API
            if texts_to_translate:
                logger.info(f"一键翻译：收集到 {len(texts_to_translate)} 个词条需要AI翻译。")
                try:
                    translation_map = self.ai_translator.batch_translate(list(texts_to_translate))
                    if translation_map:
                        logger.info(f"一键翻译：AI批量翻译成功，返回 {len(translation_map)} 个结果。")
                        
                        # 3. 回填翻译结果
                        for i, actor in enumerate(translated_cast):
                            # 更新演员名
                            original_name = actor.get('name', '').strip()
                            if original_name in translation_map:
                                translated_cast[i]['name'] = translation_map[original_name]
                            
                            # 更新角色名
                            original_role = actor.get('role', '').strip()
                            if original_role in translation_map:
                                translated_cast[i]['role'] = translation_map[original_role]
                            
                            # 只要有任何一项被翻译，就更新状态
                            if translated_cast[i].get('name') != actor.get('name') or translated_cast[i].get('role') != actor.get('role'):
                                translated_cast[i]['matchStatus'] = '已翻译'
                        
                        ai_translation_succeeded = True
                    else:
                        logger.warning("一键翻译：AI批量翻译未返回结果，将降级。")
                except Exception as e:
                    logger.error(f"一键翻译：调用AI批量翻译时出错: {e}，将降级。", exc_info=True)

        # 如果AI翻译未启用或失败，则降级到传统引擎
        if not ai_translation_succeeded:
            if self.config.get("ai_translation_enabled", False):
                logger.info("一键翻译：AI翻译失败，降级到传统引擎逐个翻译。")
            else:
                logger.info("一键翻译：AI未启用，使用传统引擎逐个翻译。")
                
            conn = self._get_db_connection()
            try:
                cursor = conn.cursor()
                for i, actor in enumerate(translated_cast):
                    actor_name_for_log = actor.get('name', '未知演员')
                    
                    # 翻译演员名
                    name_to_translate = actor.get('name', '').strip()
                    if name_to_translate and not utils.contains_chinese(name_to_translate):
                        translated_name = actor_utils.translate_actor_field(name_to_translate, "演员名(一键翻译)", name_to_translate, cursor)
                        if translated_name and translated_name != name_to_translate:
                            translated_cast[i]['name'] = translated_name
                            actor_name_for_log = translated_name

                    # 翻译角色名
                    role_to_translate = actor.get('role', '').strip()
                    if role_to_translate and not utils.contains_chinese(role_to_translate):
                        translated_role = actor_utils.translate_actor_field(role_to_translate, "角色名(一键翻译)", actor_name_for_log, cursor)
                        if translated_role and translated_role != role_to_translate:
                            translated_cast[i]['role'] = translated_role

                    if translated_cast[i].get('name') != actor.get('name') or translated_cast[i].get('role') != actor.get('role'):
                        translated_cast[i]['matchStatus'] = '已翻译'

                conn.commit()
            except Exception as e:
                logger.error(f"一键翻译（降级模式）时发生错误: {e}", exc_info=True)
                if conn: conn.rollback()
            finally:
                if conn: conn.close()

        logger.info("一键翻译完成。")
        return translated_cast
