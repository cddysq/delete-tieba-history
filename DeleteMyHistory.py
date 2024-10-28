import abc
import copy
import json
import logging
import re
import sys
import time
import traceback
import typing

import bs4
import requests
import toml
import threading
import typing_extensions

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


class HashableDict(dict):
    def __hash__(self):
        return hash(tuple(sorted(self.items())))


class ModuleConfig(typing_extensions.TypedDict):
    enable: bool
    start_page: int
    max_error_count: int


default_module_config: ModuleConfig = {
    'enable': False,  # 默认禁用
    'start_page': 1,  # 默认从第一页开始
    'max_error_count': 3  # 默认最大错误次数为 3
}


class GlobalConfig(typing_extensions.TypedDict):
    user_agent: str
    cookie_file: str

    thread: ModuleConfig
    reply: ModuleConfig
    followed_ba: ModuleConfig
    concern: ModuleConfig
    fan: ModuleConfig


class Module:
    _name: str
    _session: requests.Session
    _config: GlobalConfig
    _module_config: ModuleConfig
    _max_error_count: int

    def __init__(self, name: str, session: requests.Session, config: GlobalConfig):
        self._name = name
        self._session = session
        self._config = config
        self._module_config = self._config.get(self._name, default_module_config)
        self._max_error_count = self._module_config.get('max_error_count', 3)

    @property
    def session(self):
        return self._session

    def _get_tbs(self):
        success = False
        resp = None
        while not success:
            try:
                resp = self._session.get("https://tieba.baidu.com/dc/common/tbs", timeout=5)
                success = True
            except Exception:
                traceback.print_exc()

        tbs = resp.json()["tbs"]
        return tbs

    def run(self):
        # 没有配置启动, 直接返回
        if not self._module_config.get('enable', False):
            return

        def remove_tbs(temp_entity: typing.Dict[str, str]) -> typing.Dict[str, str]:
            # tbs 是随机生成的, 需要去掉之后再去重
            temp_entity = copy.deepcopy(temp_entity)
            if 'tbs' in temp_entity:
                del temp_entity['tbs']
            return temp_entity

        current_page = self._module_config.get('start_page', 1)
        deleted_entity = set()
        error_count = 0

        logger.info(f'current in module [{self._name}]')
        while True:
            current_page_entity = self._collect(current_page)

            if len(current_page_entity) == 0:
                # 全部删除干净了
                logger.info(f'all entity in module [{self._name}] are all deleted')
                return

            if len(set([HashableDict(remove_tbs(i)) for i in current_page_entity]).difference(deleted_entity)) == 0:
                # 当前页面全部都是已经删除过的, 跳到下一页, (百度的神奇 BUG, 只有帖子/回复会出现这种情况)
                current_page += 1
                logger.info(f'no more new entity in page [{current_page - 1}], switch to page [{current_page}]')
                continue

            for entity in current_page_entity:
                no_tbs_entity = HashableDict(remove_tbs(entity))

                if no_tbs_entity not in deleted_entity:
                    deleted_entity.add(no_tbs_entity)

                    logger.info(f"now deleting [{entity}], in page [{current_page}]")
                    resp, stop = self._delete(entity)
                    # 处理响应，解码错误信息
                    if resp is not None:
                        try:
                            response_json = resp.json()
                            if response_json.get('no') == 0:
                                logger.info(f"Successfully deleted user: {entity['id']}")
                                error_count = 0
                            else:
                                logger.error(f"Failed to delete user: {entity['id']},  full response: {response_json}")
                                error_count += 1
                        except json.JSONDecodeError:
                            logger.error(f"Failed to parse response for user: {entity['id']}, response: {resp.text}")
                            error_count += 1
                    else:
                        logger.error(f"Failed to delete user: {entity['id']}, no response received.")
                        error_count += 1
                    # 检查是否超过最大错误次数
                    if error_count >= self._max_error_count:
                        logger.error(f"Reached maximum error count ({self._max_error_count}), stopping execution.")
                        stop = True  # 设置 stop 为 True，立即停止

                    if stop:
                        logger.info(f"limit exceeded in [{self._name}], exiting")
                        sys.exit(-1)

                    # 间隔调用接口
                    time.sleep(1)

    @abc.abstractmethod
    def _collect(self, page: int) -> typing.List[typing.Dict[str, str]]:
        raise NotImplementedError("")

    @abc.abstractmethod
    def _delete(self, entity: typing.Any) -> typing.Tuple[requests.Response, bool]:
        raise NotImplementedError("")


class ThreadModule(Module):
    def __init__(self, session: requests.Session, config: GlobalConfig):
        super().__init__("thread", session, config)

    def _collect(self, page: int) -> typing.List[typing.Dict[str, str]]:
        tid_exp = re.compile(r"/([0-9]+)")
        pid_exp = re.compile(r"pid=([0-9]+)")

        resp = self._session.get("https://tieba.baidu.com/i/i/my_tie", params={'pn': page})

        html = bs4.BeautifulSoup(resp.text, "lxml")
        elements = html.find_all(name="a", attrs={"class": "thread_title"})

        current_page_thread = []
        for element in elements:
            thread = element.get("href")
            thread_dict = dict()
            thread_dict["tid"] = tid_exp.findall(thread)[0]
            thread_dict["pid"] = pid_exp.findall(thread)[0]
            current_page_thread.append(thread_dict)
        return current_page_thread

    def _delete(self, entity: typing.Dict[str, str]) -> typing.Tuple[requests.Response, bool]:
        url = "https://tieba.baidu.com/f/commit/post/delete"

        post_data = copy.deepcopy(entity)
        post_data["tbs"] = self._get_tbs()
        resp = self._session.post(url, data=post_data)

        return resp, resp.json()["err_code"] == 220034


class ReplyModule(Module):
    def __init__(self, session: requests.Session, config: GlobalConfig):
        super().__init__("reply", session, config)

    def _collect(self, page: int) -> typing.List[typing.Dict[str, str]]:
        tid_exp = re.compile(r"/([0-9]+)")
        pid_exp = re.compile(r"pid=([0-9]+)")  # 主题贴和回复都为 pid
        cid_exp = re.compile(r"cid=([0-9]+)")  # 楼中楼为 cid

        resp = self._session.get("https://tieba.baidu.com/i/i/my_reply", params={'pn': page})

        html = bs4.BeautifulSoup(resp.text, "lxml")
        elements = html.find_all(name="a", attrs={"class": "b_reply"})
        current_page_reply = []

        for element in elements:
            reply = element.get("href")
            if reply.find("pid") != -1:
                tid = tid_exp.findall(reply)
                pid = pid_exp.findall(reply)
                cid = cid_exp.findall(reply)
                reply_dict = dict()
                reply_dict["tid"] = tid[0]

                if cid and cid[0] != "0":  # 如果 cid != 0, 这个回复是楼中楼, 否则是一整楼的回复
                    reply_dict["pid"] = cid[0]
                else:
                    reply_dict["pid"] = pid[0]
                current_page_reply.append(reply_dict)
        return current_page_reply

    def _delete(self, entity: typing.Dict[str, str]) -> typing.Tuple[requests.Response, bool]:
        url = "https://tieba.baidu.com/f/commit/post/delete"

        post_data = copy.deepcopy(entity)
        post_data["tbs"] = self._get_tbs()
        resp = self._session.post(url, data=post_data)
        return resp, resp.json()["err_code"] == 220034


class FollowedBaModule(Module):
    def __init__(self, session: requests.Session, config: GlobalConfig):
        super().__init__("followed_ba", session, config)

    def _collect(self, page: int) -> typing.List[typing.Dict[str, str]]:
        ba_list = []
        resp = self._session.get("https://tieba.baidu.com/f/like/mylike", params={'pn': page})

        html = bs4.BeautifulSoup(resp.text, "lxml")
        elements = html.find_all(name="span")
        for element in elements:
            ba_dict = dict()
            ba_dict["fid"] = element.get("balvid")
            ba_dict["tbs"] = element.get("tbs")
            ba_dict["fname"] = element.get("balvname")
            ba_list.append(ba_dict)
        return ba_list

    def _delete(self, entity: typing.Dict[str, str]) -> typing.Tuple[requests.Response, bool]:
        url = "https://tieba.baidu.com/f/like/commit/delete"
        resp = self._session.post(url, data=entity)
        return resp, False


class ConcernModule(Module):
    def __init__(self, session: requests.Session, config: GlobalConfig):
        super().__init__("concern", session, config)

    def _collect(self, page: int) -> typing.List[typing.Dict[str, str]]:
        concern_list = []

        resp = self._session.get("https://tieba.baidu.com/i/i/concern", params={'pn': page})

        html = bs4.BeautifulSoup(resp.text, "lxml")
        elements = html.find_all(name="input", attrs={"class": "btn_unfollow"})
        logger.info(f'Page {page} - Found {len(elements)} concern users')
        for element in elements:
            concern_dict = dict()
            concern_dict["cmd"] = "unfollow"
            concern_dict["tbs"] = element.get("tbs")
            concern_dict["id"] = element.get("portrait")
            concern_list.append(concern_dict)
        return concern_list

    def _delete(self, entity: typing.Dict[str, str]) -> typing.Tuple[requests.Response, bool]:
        url = "https://tieba.baidu.com/home/post/unfollow"
        resp = self._session.post(url, data=entity)
        return resp, False


class FanModule(Module):
    def __init__(self, session: requests.Session, config: GlobalConfig):
        super().__init__("fan", session, config)

    def _collect(self, page: int) -> typing.List[typing.Dict[str, str]]:
        fan_list = []
        tbs_exp = re.compile(r"tbs : '([0-9a-zA-Z]{16})'")  # 居然还有一个短版 tbs.... 绝了

        resp = self._session.get("https://tieba.baidu.com/i/i/fans", params={'pn': page})

        tbs = tbs_exp.findall(resp.text)[0]
        html = bs4.BeautifulSoup(resp.text, "lxml")
        elements = html.find_all(name="input", attrs={"class": "btn_follow"})
        for element in elements:
            fan_dict = dict()
            fan_dict["cmd"] = "add_black_list"
            fan_dict["tbs"] = tbs
            fan_dict["portrait"] = element.get("portrait")
            fan_list.append(fan_dict)
        return fan_list

    def _delete(self, entity: typing.Dict[str, str]) -> typing.Tuple[requests.Response, bool]:
        url = "https://tieba.baidu.com/i/commit"
        resp = self._session.post(url, data=entity)
        return resp, False


def load_cookie(session: requests.Session, raw_cookie: str) -> requests.Session:
    for cookie in raw_cookie.split(';'):
        cookie = cookie.strip()

        if '=' in cookie:
            name, value = cookie.split('=', 1)
            session.cookies[name] = value
    return session


def validate_cookie(session: requests.Session):
    resp = session.get('https://tieba.baidu.com/i/i/my_tie', allow_redirects=False)
    return resp.status_code == 200

class DeleteMyHistory:
    def __init__(self, log_callback=None):
        self.session = None
        self.config = None
        self.running = False
        self.log_callback = log_callback  # 用于将日志输出到 GUI 或控制台

    def load_config(self, config_path: str, raw_cookie: str):
        """加载配置文件和 Cookie"""
        try:
            with open(config_path, 'r') as f:
                self.config = toml.load(f)

            self.session = requests.session()
            self.session = load_cookie(self.session, raw_cookie)  # 直接使用传入的 Cookie 字符串

            user_agent = self.config.get('user_agent', None)
            if user_agent:
                self.session.headers["User-Agent"] = user_agent

            if not validate_cookie(self.session):
                self.log("cookie expired, please update it", level="fatal")
                raise ValueError("Cookie 已过期，请更新 Cookie")

            self.log("配置文件和 Cookie 加载成功")
        except Exception as e:
            self.log(f"加载配置文件或 Cookie 失败: {e}", level="error")
            raise e

    def log(self, message, level="info"):
        """将日志输出到控制台和 GUI"""
        if level == "info":
            logger.info(message)
        elif level == "error":
            logger.error(message)
        elif level == "fatal":
            logger.fatal(message)

        # 如果有 GUI 的日志回调函数，调用它
        if self.log_callback:
            self.log_callback(message)

    def run_module(self, module_name: str):
        """根据模块名称运行对应的模块"""
        if not self.running:
            self.log("请先启动任务", level="error")
            return

        module_mapping = {
            "ThreadModule": ThreadModule,
            "ReplyModule": ReplyModule,
            "FollowedBaModule": FollowedBaModule,
            "ConcernModule": ConcernModule,
            "FanModule": FanModule
        }

        if module_name not in module_mapping:
            self.log(f"未知模块: {module_name}", level="error")
            return

        module_class = module_mapping[module_name]
        module = module_class(self.session, self.config)

        self.log(f"开始运行模块: {module_name}")
        module.run()

    def start(self):
        """启动任务"""
        self.running = True
        self.log("任务启动")

    def stop(self):
        """终止任务"""
        self.running = False
        self.log("任务终止")
        sys.exit(0)

    def run_module_in_thread(self, module_name: str):
        """在单独的线程中运行模块"""
        thread = threading.Thread(target=self.run_module, args=(module_name,))
        thread.start()


def main():
    with open('config.toml', 'r') as f:
        config: GlobalConfig = toml.load(f)

    cookie_file = config.get('cookie_file', './cookie.txt')
    with open(cookie_file, 'r') as f:
        raw_cookie = f.read()

    session = requests.session()
    session = load_cookie(session, raw_cookie)

    user_agent = config.get('user_agent', None)
    if user_agent:
        session.headers["User-Agent"] = user_agent

    if not validate_cookie(session):
        logger.fatal('cookie expired, please update it')
        sys.exit(-1)

    module_constructors: typing.List[typing.Callable[[requests.Session, GlobalConfig], Module]] = [
        ThreadModule, ReplyModule, FollowedBaModule, ConcernModule, FanModule
    ]

    for module_constructor in module_constructors:
        module = module_constructor(session, config)
        module.run()


if __name__ == "__main__":
    main()