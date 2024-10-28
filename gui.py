import tkinter as tk
import traceback
from tkinter import scrolledtext, messagebox
import threading
import logging
import toml
from DeleteMyHistory import DeleteMyHistory  # 导入你的业务逻辑类

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

class GUI:
    def __init__(self, root):
        self.root = root
        self.root.title("贴吧管理工具")

        # 设置窗口最小尺寸
        self.root.minsize(500, 400)

        # 创建 DeleteMyHistory 实例，并传入日志回调函数
        self.history_manager = DeleteMyHistory(log_callback=self.log_to_gui)

        # 配置文件路径
        self.config_path = './config.toml'

        # 创建多行文本框用于输入 Cookie
        self.cookie_label = tk.Label(root, text="请输入Cookie:")
        self.cookie_label.grid(row=0, column=0, padx=10, pady=10, sticky="e")  # 右对齐

        self.cookie_text = scrolledtext.ScrolledText(root, width=50, height=8)
        self.cookie_text.grid(row=0, column=1, padx=10, pady=10, sticky="w")  # 左对齐

        # 创建复选框用于选择模块
        self.module_label = tk.Label(root, text="请选择功能:")
        self.module_label.grid(row=1, column=0, padx=10, pady=10, sticky="ne")  # 右对齐，靠上

        # 使用 Frame 来包裹复选框，方便布局
        self.module_frame = tk.Frame(root)
        self.module_frame.grid(row=1, column=1, padx=10, pady=10, sticky="w")

        # 模块名称映射表：将 config.toml 中的模块名称映射到 GUI 中的模块名称
        self.module_mapping = {
            "thread": "ThreadModule",
            "reply": "ReplyModule",
            "followed_ba": "FollowedBaModule",
            "concern": "ConcernModule",
            "fan": "FanModule"
        }

        self.module_vars = {
            "ThreadModule": tk.IntVar(),
            "ReplyModule": tk.IntVar(),
            "FollowedBaModule": tk.IntVar(),
            "ConcernModule": tk.IntVar(),
            "FanModule": tk.IntVar()
        }

        # 增加 padx 和 pady 来调整复选框的间距
        self.thread_check = tk.Checkbutton(self.module_frame, text="清理帖子", variable=self.module_vars["ThreadModule"])
        self.thread_check.grid(row=0, column=0, padx=10, sticky="w")

        self.reply_check = tk.Checkbutton(self.module_frame, text="清理回复", variable=self.module_vars["ReplyModule"])
        self.reply_check.grid(row=0, column=1, padx=10, sticky="w")

        self.followed_ba_check = tk.Checkbutton(self.module_frame, text="清理关注的吧", variable=self.module_vars["FollowedBaModule"])
        self.followed_ba_check.grid(row=0, column=3, padx=10, sticky="w")

        self.concern_check = tk.Checkbutton(self.module_frame, text="清理关注", variable=self.module_vars["ConcernModule"])
        self.concern_check.grid(row=1, column=0, padx=10, sticky="w")

        self.fan_check = tk.Checkbutton(self.module_frame, text="清理粉丝", variable=self.module_vars["FanModule"])
        self.fan_check.grid(row=1, column=1, padx=10, sticky="w")

        # 创建日志窗口
        self.log_text = scrolledtext.ScrolledText(root, width=60, height=10)
        self.log_text.grid(row=3, column=0, columnspan=2, padx=10, pady=10)

        # 创建确认执行和终止执行按钮
        self.button_frame = tk.Frame(root)
        self.button_frame.grid(row=4, column=0, columnspan=2, pady=10)

        self.run_button = tk.Button(self.button_frame, text="确认执行", width=15, command=self.run)
        self.run_button.grid(row=0, column=0, padx=10)

        self.stop_button = tk.Button(self.button_frame, text="终止执行", width=15, command=self.stop)
        self.stop_button.grid(row=0, column=1, padx=10)

        # 初始化时加载配置文件
        self.load_config()

    def log_to_gui(self, message):
        """直接将日志输出到 GUI 的日志窗口"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def load_config(self):
        """加载配置文件，初始化复选框状态"""
        try:
            # 读取配置文件
            with open(self.config_path, 'r') as f:
                config = toml.load(f)

            # 根据配置文件中的 enable 状态设置复选框
            for config_module, gui_module in self.module_mapping.items():
                if config_module in config and 'enable' in config[config_module]:
                    self.module_vars[gui_module].set(1 if config[config_module]['enable'] else 0)

            self.log_to_gui("加载上次执行功能成功")

        except Exception as e:
            self.log_to_gui(f"加载配置文件失败: {e}")
            messagebox.showerror("错误", f"加载配置文件失败: {e}")

    def update_config(self, selected_modules):
        """根据用户选择的模块动态更新配置文件"""
        try:
            # 读取配置文件
            with open(self.config_path, 'r') as f:
                config = toml.load(f)

            # 更新配置文件中的 enable 字段
            for config_module, gui_module in self.module_mapping.items():
                if config_module in config:
                    config[config_module]['enable'] = self.module_vars[gui_module].get() == 1  # 根据复选框状态更新 enable

            # 将更新后的配置写回文件
            with open(self.config_path, 'w') as f:
                toml.dump(config, f)

            self.log_to_gui("配置文件已更新")

        except Exception as e:
            self.log_to_gui(f"更新配置文件失败: {e}")
            messagebox.showerror("错误", f"更新配置文件失败: {e}")

    def run(self):
        """确认执行"""
        cookie = self.cookie_text.get("1.0", tk.END).strip()  # 获取多行文本框中的 Cookie

        if not cookie:
            messagebox.showerror("错误", "Cookie 不能为空")
            return

        # 获取用户选择的模块
        selected_modules = [module for module, var in self.module_vars.items() if var.get() == 1]

        if not selected_modules:
            messagebox.showerror("错误", "请至少选择一个模块")
            return

        try:
            # 更新配置文件，确保用户选择的模块被启用
            self.update_config(selected_modules)

            # 加载更新后的配置文件
            self.history_manager.load_config(self.config_path, cookie)
            self.history_manager.start()

            # 逐个运行用户选择的模块
            for module_name in selected_modules:
                self.run_module(module_name)

        except Exception as e:
            self.log_to_gui(f"任务启动失败: {e}")
            messagebox.showerror("错误", f"任务启动失败: {e}")

    def run_module(self, module_name):
        """运行指定的模块"""
        if not self.history_manager.running:
            self.log_to_gui("请先点击确认执行")
            return

        # 启动后台线程运行模块
        threading.Thread(target=self.history_manager.run_module, args=(module_name,)).start()

    def stop(self):
        """终止执行"""
        self.history_manager.stop()
        self.log_to_gui("任务已终止")

def main():
    try:
        root = tk.Tk()
        app = GUI(root)
        root.mainloop()
    except KeyboardInterrupt:
        # 处理用户手动中断的情况
        print("程序已被用户中断")
    except Exception as e:
        # 捕获其他异常
        print(f"程序发生异常: {e}")
        traceback.print_exc()
    finally:
        # 在这里可以进行一些清理工作
        print("程序已退出")

if __name__ == "__main__":
    main()
