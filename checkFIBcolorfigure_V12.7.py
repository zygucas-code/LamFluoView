# -*- coding: utf-8 -*-
"""
Created on Thu Mar  6 16:13:22 2025
@author: Yan Zeng @ ibp
终极优化版本
核心修复 & 新增功能：
1. 彻底解决锁定后缩放/平移卡顿问题（根治重复矩阵运算）
2. 锁定瞬间：生成背景同尺寸、像素级对齐归一化荧光图
3. 锁定瞬间：**覆盖内存中原荧光图**，全程无变换运算，极致流畅
4. 自动保存归一化原始荧光文件（xxx_normalized_fluo.jpg）
5. 解锁无损还原所有原始状态，零偏差、无功能丢失
"""

# -*- coding: utf-8 -*-
"""
透明图片查看器 - 支持配置文件读取（仅读取不写入）
配置文件(config.txt)需手动创建和编辑，参数缺失时使用程序预设值
"""


import math
import sys
import os
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QDoubleSpinBox, QComboBox, QLabel, QHBoxLayout,
    QVBoxLayout, QFileDialog, QWidget, QShortcut
)
from PyQt5.QtCore import Qt, QPointF, QRect
from PyQt5.QtGui import QPixmap, QPainter, QImage, QTransform, QKeySequence, QPen, QFont
from PIL import Image, ImageEnhance
import contextlib
import time

# 解决大图片加载限制
Image.MAX_IMAGE_PIXELS = None


@contextlib.contextmanager
def serialem_session():
    """创建一个 SerialEM 会话的上下文管理器"""
    try:
        yield sem  # 返回 SerialEM 模块供使用
    finally:
        try:
            # 尝试关闭会话，捕获可能的错误
            sem.Exit()
        except Exception as e:
            # 抑制错误，可以选择记录日志或简单忽略
            print(f"关闭SerialEM会话: {e}")


def GetUniqueID():
    with serialem_session() as sem:
        UniqueID = sem.GetUniqueNavID()
        print("UniqueID#############:", UniqueID)
        return int(UniqueID)


def SaveBufferToFile(filepath=r'test1.jpg'):
    with serialem_session() as sem:
        CurrentBuffer = sem.ReportCurrentBuffer()
        sem.SaveToOtherFile(CurrentBuffer[0], 'JPG', 'NONE', filepath)


def AddPoint(x, y, UniqueID):
    with serialem_session() as sem:
        CurrentBuffer = sem.ReportCurrentBuffer()
        sem.AddImagePosAsNavPoint(CurrentBuffer[0], int(x), int(y), -990, UniqueID)


class TransparentImageViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # 初始化参数（后续会被配置文件覆盖，无配置时使用这些预设值）
        self.image_path = None
        self.image = None
        self.bg_image_path = None
        self.bg_image = None
        self.opacity = 1.0
        self.previous_opacity = 1.0
        self.is_transparent = False
        self.image_offset = QPointF(0, 0)
        self.bg_offset = QPointF(0.0, 0.0)
        self.is_locked = False
        self.add_points_mode = False
        self.dragging = False
        self.old_pos = None
        self.points = []
        self.lock_ratio = 1.0
        self.lock_image_state = None  # 保存锁定前的完整原始状态
        self.uniqueID = 0
        self.angle = 0  # 旋转角度预设值
        self.flip_image = 0  # 默认不翻转
        self.drag_threshold = 2  # 判定为拖动的最小像素距离
        self.mouse_moved = False  # 记录鼠标是否移动
        self.initial_click_pos = None  # 初始点击位置

        # 新增：锁定归一化后的荧光图（和背景图同尺寸）
        self.normalized_fluo_image = None

        # 确定配置文件路径
        if getattr(sys, 'frozen', False):
            # 打包后环境：exe所在目录
            self.exe_dir = os.path.dirname(sys.executable)
            self.config_path = os.path.join(self.exe_dir, 'config.txt')
        else:
            # 开发环境：脚本所在目录
            self.config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.txt')

        # 加载配置（无配置文件则使用预设值）
        self.load_config()

        # 从配置获取关键参数（已确保有默认值）
        self.serialemPythonModulesPath = self.config['serialemPythonModulesPath']
        print(f"读取到的serialem路径: {self.serialemPythonModulesPath}")

        # 导入serialem模块
        try:
            self.import_serialem()
        except ImportError as e:
            # 处理导入失败的情况（例如显示提示并退出）
            print(f"致命错误：{e}")    

        # 初始化UI
        self.setFixedSize(1000, 1150)
        self.initUI()

    def load_config(self):
        """仅读取配置文件，不自动创建，参数缺失时使用预设值"""
        # 预设配置参数（所有可能用到的参数都在这里定义默认值）
        self.config = {
            'angle': 1.0,  # 旋转角度
            'ellipse_width': 20.0,  # 椭圆宽度
            'ellipse_height_width_ratio': 2 ,       #>1  , e.g.  1/cos60 = 2  
            'ellipse_height': 20.0,  # 椭圆高度
            'ellipse_angle': 4.5,  # 椭圆倾角（预设为4.5度，对应原90-85.5）
            'serialemPythonModulesPath': "" , # serialem模块路径
            'flip_image': 0 , # 默认不翻转

            'opacity_initial': 50.0,
            'scale_initial': 100.0,
            'bg_scale_initial': 5.0,
            'ia_initial': 1.2,
            'ps_initial': 20.2,
            'stretch_angle': 0.0,        # 拉伸方向角度（度）
            'stretch_factor': 1.0,       # 拉伸倍数（1.0 = 无拉伸，>1 = 拉长，<1 = 压缩

        }

        # 定义参数类型映射（用于类型转换）
        type_mapping = {
            'angle': float,
            'ellipse_width': float,
            'ellipse_height_width_ratio': float ,
            'ellipse_height': float,
            'ellipse_angle': float,
            'serialemPythonModulesPath': str,
            'flip_image': int,
            'opacity_initial': float,
            'scale_initial': float,
            'bg_scale_initial': float,
            'ia_initial': float,
            'ps_initial': float,
            'stretch_angle': float,
            'stretch_factor': float,
        }

        # 仅在配置文件存在时读取
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or '=' not in line:
                            continue  # 跳过空行和无效行
                        
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()

                        # 仅处理已知参数
                        if key in self.config:
                            # 尝试转换为正确类型
                            try:
                                self.config[key] = type_mapping[key](value)
                            except ValueError:
                                print(f"配置文件中参数 {key} 格式错误，使用默认值")
            except Exception as e:
                print(f"读取配置文件出错: {e}，将使用预设值")

            self.config['ellipse_height'] = self.config['ellipse_width'] * self.config['ellipse_height_width_ratio']
            self.flip_image = self.config.get('flip_image', 0)  # 获取翻转状态，默认为0


    def import_serialem(self):
        """导入serialem模块，路径从配置文件获取"""
        global sem  # 声明为全局变量供其他函数使用

        # 检查配置的路径是否有效
        if not self.serialemPythonModulesPath or not os.path.exists(self.serialemPythonModulesPath):
            # 路径无效时提示用户选择
            msg = "未找到serialem模块，请手动选择serialem.pyd文件"
            print(msg)
            self.serialemPythonModulesPath, _ = QFileDialog.getOpenFileName(
                None, "选择serialem模块", "", "Python扩展模块 (*.pyd)"
            )
            if not self.serialemPythonModulesPath:
                raise FileNotFoundError("未选择serialem模块，程序无法运行")

        # 导入模块
        try:
            serialem_dir = os.path.dirname(self.serialemPythonModulesPath)
            if serialem_dir not in sys.path:
                sys.path.insert(0, serialem_dir)
                print(sys.path)
                time.sleep(1)
            from importlib.util import spec_from_file_location, module_from_spec
            spec = spec_from_file_location('serialem', self.serialemPythonModulesPath)
            sem = module_from_spec(spec)
            spec.loader.exec_module(sem)

            print(f"成功导入serialem模块: {self.serialemPythonModulesPath}")
        except Exception as e:
            raise ImportError(f"导入serialem模块失败: {e}")

    def initUI(self):
        self.control_widget = QWidget()
        # 批量设置控件样式：字体、宽度等
        self.control_widget.setStyleSheet("""
            QPushButton {
                font-family: 微软雅黑;
                font-size: 16pt;
                height: 50px;
                width: 150px;
            }
            QDoubleSpinBox {
                font-family: 微软雅黑;
                font-size: 16pt;
                height: 50px;
                width: 150px;
            }
            QLabel {
                font-family: 微软雅黑;
                height: 50px;
                font-size: 16pt;
            }
        """)

        self.control_widget.setStyleSheet("background-color: rgba(255, 255, 200, 1);")
        self.control_layout = QVBoxLayout()

        # 第一行：背景加载按钮、标题、控制按钮
        self.top_layout = QHBoxLayout()
        self.load_bg_button = QPushButton("加载背景图片")
        self.load_bg_button.clicked.connect(self.load_bg_image)
        self.top_layout.addWidget(self.load_bg_button)
        
        #QDoubleSpinBox.setKeyboardTracking(False)  # 关闭spinbox的键盘追踪，提升输入体验
        # 背景图缩放控件
        self.bg_scale_spinbox = QDoubleSpinBox()
        self.bg_scale_spinbox.setRange(1, 1000)
        self.bg_scale_spinbox.setValue(self.config.get('bg_scale_initial', 5.0))
        self.bg_scale_spinbox.setKeyboardTracking(False)
        self.bg_scale_spinbox.valueChanged.connect(self.update_bg_scale)
        self.top_layout.addWidget(self.bg_scale_spinbox)
        self.top_layout.addWidget(QLabel("背景缩放"))

        self.title_label = QLabel("===========透明图片查看器===========")
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: black;")
        self.top_layout.addWidget(self.title_label)

        self.top_layout.addStretch()
        self.minimize_button = QPushButton("—")
        self.minimize_button.clicked.connect(self.showMinimized)
        self.top_layout.addWidget(self.minimize_button)

        self.close_button = QPushButton("×")
        self.close_button.clicked.connect(self.close)
        self.top_layout.addWidget(self.close_button)

        self.control_layout.addLayout(self.top_layout)

        # 第二行：操作控件
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(1)

        # 透明图加载按钮
        self.load_button = QPushButton("加载图片")
        self.load_button.clicked.connect(self.load_image)
        bottom_layout.addWidget(self.load_button)

        # 拉伸角度和拉伸程度控制
        self.stretch_angle_spinbox = QDoubleSpinBox()
        self.stretch_angle_spinbox.setRange(-180, 180)
        self.stretch_angle_spinbox.setValue(self.config.get('stretch_angle', 0.0))
        self.stretch_angle_spinbox.setSingleStep(0.1)
        self.stretch_angle_spinbox.setKeyboardTracking(False)
        self.stretch_angle_spinbox.valueChanged.connect(self.update_image)

        self.stretch_factor_spinbox = QDoubleSpinBox()
        self.stretch_factor_spinbox.setRange(0.1, 3.0)
        self.stretch_factor_spinbox.setValue(self.config.get('stretch_factor', 1.0))
        self.stretch_factor_spinbox.setSingleStep(0.05)
        self.stretch_factor_spinbox.setKeyboardTracking(False)
        self.stretch_factor_spinbox.valueChanged.connect(self.update_image)

        bottom_layout.addWidget(QLabel("    拉伸角:"))
        bottom_layout.addWidget(self.stretch_angle_spinbox)
        bottom_layout.addWidget(QLabel("    拉伸比:"))
        bottom_layout.addWidget(self.stretch_factor_spinbox)

        # 旋转控件
        self.rotate_spinbox = QDoubleSpinBox()
        self.rotate_spinbox.setRange(-360, 360)
        self.rotate_spinbox.setValue(self.config.get('angle', 0.0))
        self.rotate_spinbox.setKeyboardTracking(False)
        self.rotate_spinbox.valueChanged.connect(self.rotate_image)
        bottom_layout.addWidget(QLabel("      旋转:")) 
        bottom_layout.addWidget(self.rotate_spinbox)
        

        # 透明度控件
        self.opacity_spinbox = QDoubleSpinBox()
        self.opacity_spinbox.setRange(0, 100)
        self.opacity_spinbox.setValue(self.config.get('opacity_initial', 50.0))
        self.opacity_spinbox.setKeyboardTracking(False)
        self.opacity_spinbox.valueChanged.connect(self.update_opacity)
        bottom_layout.addWidget(QLabel("      透明度:")) 
        bottom_layout.addWidget(self.opacity_spinbox)
        

        # 透明图缩放控件
        self.scale_spinbox = QDoubleSpinBox()
        self.scale_spinbox.setRange(1, 5000)
        self.scale_spinbox.setValue(self.config.get('scale_initial', 100.0))
        self.scale_spinbox.setKeyboardTracking(False)
        self.scale_spinbox.valueChanged.connect(self.update_scale)
        bottom_layout.addWidget(QLabel("      缩放:")) 
        bottom_layout.addWidget(self.scale_spinbox)
        

        # flip选择控件
        self.flip_combobox = QComboBox()
        self.flip_combobox.addItems(["Normal (0)", "Flipped (1)"])
        self.flip_combobox.setCurrentIndex(self.flip_image)
        self.flip_combobox.currentIndexChanged.connect(self.on_flip_changed)
        bottom_layout.addWidget(QLabel("      Flip:"))
        bottom_layout.addWidget(self.flip_combobox)

        # 透明度切换按钮
        self.toggle_transparency_button = QPushButton("切换透明度 (Ctrl+H)")
        self.toggle_transparency_button.setCheckable(True)
        self.toggle_transparency_button.clicked.connect(self.toggle_transparency)
        bottom_layout.addWidget(self.toggle_transparency_button)

        # 第三行：操作控件
        bottom2_layout = QHBoxLayout()

        self.IA_spinbox = QDoubleSpinBox()
        self.IA_spinbox.setRange(0.1, 10)
        self.IA_spinbox.setValue(self.config.get('ia_initial', 1.2))
        self.IA_spinbox.setKeyboardTracking(False)
        bottom2_layout.addWidget(self.IA_spinbox)
        bottom2_layout.addWidget(QLabel("IA/um"))

        self.PS_spinbox = QDoubleSpinBox()
        self.PS_spinbox.setRange(0.001, 10000)
        self.PS_spinbox.setValue(self.config.get('ps_initial', 20.2))
        self.PS_spinbox.setKeyboardTracking(False)
        bottom2_layout.addWidget(self.PS_spinbox)
        bottom2_layout.addWidget(QLabel("pixel size/A"))

        self.lock_button = QPushButton("锁定")
        self.lock_button.setCheckable(True)
        self.lock_button.clicked.connect(self.toggle_lock)
        bottom2_layout.addWidget(self.lock_button)

        self.add_points_button = QPushButton("add points")
        self.add_points_button.setCheckable(True)
        self.add_points_button.clicked.connect(self.toggle_add_points_mode)
        bottom2_layout.addWidget(self.add_points_button)

        self.control_layout.addLayout(bottom_layout)
        self.control_layout.addLayout(bottom2_layout)
        self.control_widget.setLayout(self.control_layout)
        self.control_widget.setFixedHeight(80)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: transparent;")
        self.image_label.setFixedSize(self.width(), self.height() - self.control_widget.height())

        self.main_layout = QVBoxLayout()
        self.main_layout.addWidget(self.control_widget)
        self.main_layout.addWidget(self.image_label)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.central_widget = QWidget()
        self.central_widget.setLayout(self.main_layout)
        self.central_widget.setStyleSheet("background-color: transparent;")
        self.setCentralWidget(self.central_widget)

        self.shortcut = QShortcut(QKeySequence("Ctrl+H"), self)
        self.shortcut.activated.connect(self.toggle_transparency)

    def load_image(self):
        self.image_path, _ = QFileDialog.getOpenFileName(self, "选择图片", "", "Images (*.png *.jpg *.bmp *.gif *.tif *.tiff)")
        if self.image_path:
            try: 
                """
                pil_image = Image.open(self.image_path).convert('RGBA')
                enhancer = ImageEnhance.Brightness(pil_image)
                pil_image = enhancer.enhance(1.2)
                enhancer = ImageEnhance.Contrast(pil_image)
                pil_image = enhancer.enhance(1.2)
                
                #self.image = QPixmap(self.image_path)
                if self.flip_image == 1:
                    pil_image = pil_image.transpose(Image.FLIP_LEFT_RIGHT)  # 水平翻转
                data = pil_image.tobytes("raw", "RGBA")
                qimage = QImage(data, pil_image.size[0], pil_image.size[1], QImage.Format_RGBA8888)
                self.image = QPixmap.fromImage(qimage)
                # 清空归一化缓存
                self.normalized_fluo_image = None
                if self.image:
                    self.opacity_spinbox.setValue(50)
                    self.update_image()

                """
                # 【修复】改用Qt原生加载，自动遵从EXIF方向，与背景图逻辑完全一致
                self.image = QPixmap(self.image_path)
                
                if self.flip_image == 1:
                    transform = QTransform().scale(-1, 1)
                    self.image = self.image.transformed(transform)

                # 清空归一化缓存
                self.normalized_fluo_image = None
                if self.image:
                    self.opacity_spinbox.setValue(50)
                    self.rotate_spinbox.setValue(self.angle)
                    self.update_image()

            except Exception as e:
                print(f"加载图片时出错: {e}")
                
            
    """
    def load_bg_image(self):
        self.bg_image = None
        # 使用配置的serialem路径拼接背景图路径（避免绝对路径）
        if self.serialemPythonModulesPath:
            sem_dir = os.path.dirname(self.serialemPythonModulesPath)
            self.bg_image_path = os.path.join(sem_dir, 'test1.jpg')
        else:
            self.bg_image_path = 'test1.jpg'  # fallback

        if self.is_locked:
            self.toggle_lock()
            self.lock_button.setChecked(False)
            self.is_locked = False
        if self.add_points_mode:
            self.toggle_add_points_mode()
            self.add_points_button.setChecked(False)
            self.add_points_mode = False
        
        SaveBufferToFile(filepath=self.bg_image_path)
        
        if os.path.exists(self.bg_image_path):
            try:
                with Image.open(self.bg_image_path) as pil_image:
                    pil_image = pil_image.convert('RGBA')
                    enhancer = ImageEnhance.Brightness(pil_image)
                    pil_image = enhancer.enhance(1.2)
                    data = pil_image.tobytes("raw", "RGBA")
                    qimage = QImage(data, pil_image.size[0], pil_image.size[1], QImage.Format_RGBA8888)
                    self.bg_image = QPixmap.fromImage(qimage)
                    # 清空归一化缓存
                    self.normalized_fluo_image = None
                    if self.bg_image:
                        self.update_image()
            except Exception as e:
                print(f"加载背景图片时出错: {e}")
        else:
            print(f"背景图片文件不存在: {self.bg_image_path}")
        
        # 重置相关参数
        self.image = None
        self.points = []
        self.image_offset = QPointF(0, 0)
        self.update_image()
        """
    def load_bg_image(self):
        self.bg_image = None
        # 使用配置的serialem路径拼接背景图路径（避免绝对路径）
        if self.serialemPythonModulesPath:
            sem_dir = os.path.dirname(self.serialemPythonModulesPath)
            self.bg_image_path = os.path.join(sem_dir, 'test1.jpg')
        else:
            self.bg_image_path = 'test1.jpg'  # fallback

        # 加载背景图前强制解锁、关闭打点模式
        if self.is_locked:
            self.toggle_lock()
            self.lock_button.setChecked(False)
            self.is_locked = False
        if self.add_points_mode:
            self.toggle_add_points_mode()
            self.add_points_button.setChecked(False)
            self.add_points_mode = False
        
        # 从SerialEM保存最新背景缓存
        SaveBufferToFile(filepath=self.bg_image_path)
        
        if os.path.exists(self.bg_image_path):
            try:
                # 纯Qt原生加载，完全原图显示，无任何提亮/对比度修改
                self.bg_image = QPixmap(self.bg_image_path)
                if self.bg_image.isNull():
                    print("背景图片读取失败（空图像）")
                    return

                # 清空归一化缓存、刷新画面
                self.normalized_fluo_image = None
                self.update_image()

            except Exception as e:
                print(f"加载背景图片时出错: {e}")
        else:
            print(f"背景图片文件不存在: {self.bg_image_path}")
        
        # 重置叠加参数
        self.image = None
        self.points = []
        self.image_offset = QPointF(0, 0)
        self.bg_offset = QPointF(0, 0)
        self.update_image()
    """
    def create_normalized_fluo_image(self):
        
        #核心归一化函数：锁定时生成和背景图**完全同尺寸、完全对齐**的荧光图
        #空白区域填充透明像素，实现两图坐标系统一
        
        if not self.image or not self.bg_image:
            return None
        
        # 1. 获取原始背景图尺寸（基准尺寸）
        bg_w = self.bg_image.width()
        bg_h = self.bg_image.height()

        # 2. 获取当前荧光图所有变换，生成最终叠合图像
        stretch_angle = self.stretch_angle_spinbox.value()
        stretch_factor = self.stretch_factor_spinbox.value()
        scale = self.scale_spinbox.value() / 100

        # 合并所有变换矩阵（拉伸+旋转+缩放）
        transform = QTransform()
        transform.translate(self.image.width()/2, self.image.height()/2)
        transform.rotate(stretch_angle)
        transform.scale(stretch_factor, 1.0)
        transform.rotate(-stretch_angle)
        transform.rotate(self.angle)
        transform.scale(scale, scale)
        transform.translate(-self.image.width()/2, -self.image.height()/2)

        # 执行变换
        transformed_fluo = self.image.transformed(transform, Qt.SmoothTransformation)

        # 3. 创建和背景图同尺寸的透明画布
        normalized_img = QImage(bg_w, bg_h, QImage.Format_ARGB32)
        normalized_img.fill(Qt.transparent)
        painter = QPainter(normalized_img)

        # 4. 将变换后的荧光图居中绘制到背景图尺寸画布（完美对齐基准）
        #draw_x = (bg_w - transformed_fluo.width()) // 2
        #draw_y = (bg_h - transformed_fluo.height()) // 2
        #painter.drawPixmap(draw_x, draw_y, transformed_fluo)

        # 新：等比例缩放到背景图尺寸
        scaled_fluo = transformed_fluo.scaled(
            bg_w, bg_h,
            Qt.KeepAspectRatio,    # 保持宽高比
            Qt.SmoothTransformation
        )
        # 居中绘制（依然有少量透明边，完全等比）
        dx = (bg_w - scaled_fluo.width()) // 2
        dy = (bg_h - scaled_fluo.height()) // 2
        painter.drawPixmap(dx, dy, scaled_fluo)

        painter.end()

        return QPixmap.fromImage(normalized_img)"""

    """  
    def create_normalized_fluo_image(self):
        
        #最终版归一化函数
        #1. 画布固定为【背景图原始尺寸】
        #2. 荧光图尺寸公式：原图尺寸 * 荧光缩放 / 背景缩放
        #3. 拖拽偏移：屏幕像素偏移 → 换算为背景图像素偏移
        #4. 位置、尺寸与UI实时显示完全对齐
        
        if not self.image or not self.bg_image:
            return None

        # ===================== 1. 读取基础参数 =====================
        # 背景图原始尺寸（最终画布尺寸，基准坐标系）
        bg_w = self.bg_image.width()
        bg_h = self.bg_image.height()

        # 缩放倍数（百分比转倍率）
        fluo_scale_ratio = self.scale_spinbox.value() / 100    # 荧光图整体缩放倍率
        bg_scale_ratio = self.bg_scale_spinbox.value() / 100    # 背景图显示缩放倍率

        # 图像形变参数：拉伸、旋转
        stretch_angle = self.stretch_angle_spinbox.value()
        stretch_factor = self.stretch_factor_spinbox.value()
        rotate_angle = self.angle

        # 外层显示画布尺寸（image_label 屏幕像素）
        label_w = self.image_label.width()
        label_h = self.image_label.height()

        # ===================== 2. 对原始荧光图做 拉伸+旋转 基础变换 =====================
        transform = QTransform()
        # 变换中心设为图像中心
        transform.translate(self.image.width() / 2, self.image.height() / 2)
        # 拉伸逻辑
        transform.rotate(stretch_angle)
        transform.scale(stretch_factor, 1.0)
        transform.rotate(-stretch_angle)
        # 旋转逻辑
        transform.rotate(rotate_angle)
        transform.translate(-self.image.width() / 2, -self.image.height() / 2)

        # 完成形变后的荧光图（未做最终缩放）
        transformed_fluo = self.image.transformed(transform, Qt.SmoothTransformation)

        # ===================== 3. 按公式计算最终荧光图尺寸 =====================
        # 公式：最终尺寸 = 形变后尺寸 * 荧光缩放倍率 / 背景缩放倍率
        final_fluo_w = transformed_fluo.width() * fluo_scale_ratio / bg_scale_ratio
        final_fluo_h = transformed_fluo.height() * fluo_scale_ratio / bg_scale_ratio

        # 缩放到目标尺寸
        final_fluo = transformed_fluo.scaled(
            int(final_fluo_w),
            int(final_fluo_h),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        # ===================== 4. 偏移量换算：屏幕偏移 → 背景图像素偏移 =====================
        # 1. 计算【外层画布】中，背景图的实际显示尺寸（屏幕像素）
        display_bg_w = bg_w * bg_scale_ratio
        display_bg_h = bg_h * bg_scale_ratio

        # 2. 屏幕偏移量（相对于外层画布）→ 换算为【背景图原始像素】偏移
        # 比例 = 屏幕偏移 / 背景图显示宽度(屏幕像素)
        offset_x = self.image_offset.x() * (bg_w / display_bg_w)
        offset_y = self.image_offset.y() * (bg_h / display_bg_h)

        # ===================== 5. 在背景图画布上绘制（居中 + 偏移） =====================
        # 创建背景图尺寸的透明画布
        normalized_img = QImage(bg_w, bg_h, QImage.Format_ARGB32)
        normalized_img.fill(Qt.transparent)
        painter = QPainter(normalized_img)

        # 基础居中坐标（背景图画布内居中）
        base_dx = (bg_w - final_fluo.width()) / 2.0
        base_dy = (bg_h - final_fluo.height()) / 2.0

        # 叠加换算后的偏移量（背景图像素单位）
        draw_x = base_dx + offset_x
        draw_y = base_dy + offset_y

        # 绘制最终荧光图
        painter.drawPixmap(draw_x, draw_y, final_fluo)
        painter.end()

        return QPixmap.fromImage(normalized_img)   """

    def create_normalized_fluo_image(self):
        """
        【优化版】先裁剪再缩放二次裁剪，低内存生成与背景图像素级对齐的归一化荧光图
        核心流程：拉伸旋转→裁剪冗余区域→缩放匹配分辨率→精准对齐裁剪
        """
        # ====================== 前置基础校验 ======================
        if not self.image or not self.bg_image:
            return QPixmap()

        # ====================== 读取所有变换参数（与原有控件逻辑完全对齐） ======================
        # 从UI控件获取基础变换参数，保留浮点精度避免截断误差
        stretch_angle = self.stretch_angle_spinbox.value()
        stretch_factor = self.stretch_factor_spinbox.value()
        rotate_angle = self.angle
        fluo_scale_ratio = self.scale_spinbox.value() / 100.0  # 荧光图缩放倍率
        bg_scale_ratio = self.bg_scale_spinbox.value() / 100.0  # 背景图缩放倍率
        device_pixel_ratio = self.devicePixelRatio()  # 高DPI适配倍率

        """# ====================== 锁定状态参数同步 ======================
        # 锁定时复用预处理的缩放比例，同步偏移量为0，保证锁定后绘制无计算开销
        if self.is_locked and self.lock_image_state:
            # 锁定时直接使用联动的缩放比例，避免重复矩阵运算
            bg_scale_ratio = self.scale_spinbox.value() / self.lock_ratio / 100.0
            # 锁定时将偏移量置零，完全复用预裁剪的荧光图
            self.image_offset = QPointF(0.0, 0.0)
            fluo_scale_ratio = self.lock_image_state['scale'] / 100.0"""

        # ====================== 步骤1：对原始荧光图做拉伸+旋转变换 ======================
        # 构建基础变换矩阵，执行顺序=缩放→旋转→平移，与原有变换逻辑完全一致
        transform = QTransform()
        """# 将变换中心设置为图像几何中心，避免旋转/拉伸后位置偏移
        transform.translate(self.image.width() / 2.0, self.image.height() / 2.0)
        # 先执行拉伸变换：旋转到拉伸方向、应用拉伸倍数、旋转回原角度
        transform.rotate(stretch_angle)
        transform.scale(stretch_factor, 1.0)
        transform.rotate(-stretch_angle)
        # 执行旋转变换
        transform.rotate(rotate_angle)
        # 恢复坐标系原点到图像左上角
        transform.translate(-self.image.width() / 2.0, -self.image.height() / 2.0)"""
        transform.translate(self.image.width() / 2.0, self.image.height() / 2.0)
        # 1. 全局旋转
        transform.rotate(rotate_angle)
        # 2. 单向拉伸
        transform.rotate(stretch_angle)
        transform.scale(stretch_factor, 1.0)
        transform.rotate(-stretch_angle)
        # 3. 等比缩放倍率
        #transform.scale(fluo_scale_ratio, fluo_scale_ratio)
        transform.translate(-self.image.width() / 2.0, -self.image.height() / 2.0)



        # 应用变换，生成拉伸+旋转后的临时荧光图，保留 SmoothTransformation 无损插值
        transformed_fluo = self.image.transformed(transform, Qt.SmoothTransformation)
        print(f"变换后荧光图尺寸: {transformed_fluo.width()} x {transformed_fluo.height()}")
        if transformed_fluo.isNull():
            return QPixmap()

        # ====================== 步骤2：计算坐标系映射关系，定位裁剪基准中心 ======================
        # 获取背景图原始尺寸，计算背景图在自身坐标系下的几何中心
        bg_original_w = self.bg_image.width()
        bg_original_h = self.bg_image.height()
        bg_center = QPointF(bg_original_w / 2.0, bg_original_h / 2.0)
        fluo_original_w = transformed_fluo.width()
        fluo_original_h = transformed_fluo.height()
        fluo_center = QPointF(fluo_original_w / 2.0, fluo_original_h / 2.0)

        # 换算平移偏移量：荧光图中心相对于背景图的真实偏移 = 屏幕像素偏移 / 背景图缩放倍率
        #offset_x = self.image_offset.x() * (bg_original_w / (self.bg_image.width() * bg_scale_ratio))
        #offset_y = self.image_offset.y() * (bg_original_h / (self.bg_image.height() * bg_scale_ratio))
        offset_x = (self.bg_offset.x() - self.image_offset.x()) / fluo_scale_ratio
        offset_y = (self.bg_offset.y() - self.image_offset.y()) / fluo_scale_ratio
        print(f"self.bg_offset.x(): {self.bg_offset.x()}, self.image_offset.x(): {self.image_offset.x()}, offset_x: {offset_x}")   
        print(f"self.bg_offset.y(): {self.bg_offset.y()}, self.image_offset.y(): {self.image_offset.y()}, offset_y: {offset_y}")

        # 映射得到荧光图上的对应裁剪中心坐标（背景图中心+校准偏移量）
        fluo_crop_center = QPointF(fluo_center.x() + offset_x, fluo_center.y() + offset_y)
        print(f"荧光图原始中心坐标: ({fluo_center.x()}, {fluo_center.y()})")
        print(f"映射后的荧光图裁剪中心坐标: ({fluo_crop_center.x()}, {fluo_crop_center.y()})")

        # ====================== 步骤3：计算首次裁剪尺寸，裁剪冗余透明区域 ======================
        # 依据两图缩放倍率比值，计算匹配背景图视野范围的荧光图裁剪尺寸
        crop_w = bg_original_w *  bg_scale_ratio / fluo_scale_ratio 
        crop_h = bg_original_h *  bg_scale_ratio / fluo_scale_ratio 

        # 计算首次裁剪区域的左上角坐标，以映射后的荧光图中心为基准
        crop_x = fluo_crop_center.x() - crop_w / 2.0
        crop_y = fluo_crop_center.y() - crop_h / 2.0

        # 校验裁剪边界，确保不会超出荧光图的有效像素范围，避免非法裁剪区域报错
        #max_crop_x = max(0.0, min(crop_x, transformed_fluo.width() - crop_w))
        #max_crop_y = max(0.0, min(crop_y, transformed_fluo.height() - crop_h))
        #crop_rect = QRectF(max_crop_x, max_crop_y, crop_w, crop_h)

        # 执行首次裁剪，去掉周围无用的透明/黑色区域，大幅降低后续内存开销
        #first_cropped = transformed_fluo.copy(crop_rect)
        #if first_cropped.isNull():
        #    return QPixmap()
        # 向上取整画布尺寸，和你之前逻辑一致，画布略大无精度丢失
        canvas_w = math.ceil(crop_w)
        canvas_h = math.ceil(crop_h)

        # 创建空白透明画布（越界部分自动填充空像素，不会改动裁剪中心）
        crop_canvas = QImage(canvas_w, canvas_h, QImage.Format_ARGB32)
        crop_canvas.fill(Qt.transparent)

        # 反向偏移绘制原图：原图超出画布的部分保留，画布外区域自动补透明，中心点零偏移
        p = QPainter(crop_canvas)
        p.drawPixmap(-crop_x, -crop_y, transformed_fluo)
        p.end()

        # 得到裁剪后图像，裁剪尺寸、中心坐标完全和计算值一致，无中心偏移
        first_cropped = QPixmap.fromImage(crop_canvas)
        if first_cropped.isNull():
            return QPixmap()
        first_cropped.save("D:\\ToBeRead\\PIBB\\20260612mito_fluor_CBItest\\20260610_mito_red\\first_cropped.jpg", "JPG", 100)
        # 更新裁剪后新的图像中心点（关键：仅平移坐标系，中心物理位置完全不变）
        new_fluo_center_x = crop_w / 2.0  #fluo_crop_center.x() - crop_x
        new_fluo_center_y = crop_h / 2.0  #fluo_crop_center.y() - crop_y
        fluo_crop_center = QPointF(new_fluo_center_x, new_fluo_center_y)
        print(f"首次裁剪后荧光图尺寸: {first_cropped.width()} x {first_cropped.height()}")
        print(f"首次裁剪后荧光图中心坐标: ({fluo_crop_center.x()}, {fluo_crop_center.y()})")

        # ====================== 步骤4：缩放荧光图，匹配背景图像素物理尺寸 ======================
        # 计算缩放因子：让荧光图的1个像素对应真实世界的尺寸，与背景图完全对齐
        scale_factor = bg_scale_ratio / fluo_scale_ratio
        target_fluo_w = first_cropped.width() / scale_factor
        target_fluo_h = first_cropped.height() / scale_factor
        print(f"target_fluo_w: {target_fluo_w}, target_fluo_h: {target_fluo_h}")

        # 无损缩放到目标分辨率，与背景图像素物理尺寸完全对齐
        scaled_fluo = first_cropped.scaled(
            int(target_fluo_w),
            int(target_fluo_h),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        if scaled_fluo.isNull():
            return QPixmap()
        
        fluo_crop_center = QPointF(fluo_crop_center.x() / scale_factor, fluo_crop_center.y() / scale_factor)

        # ====================== 步骤5：二次精准裁剪，与背景图完成像素级对齐 ======================
        # 缩放后中心点已同步乘scale_factor，直接使用当前最新中心点
        final_crop_x = fluo_crop_center.x() - bg_original_w / 2.0
        final_crop_y = fluo_crop_center.y() - bg_original_h / 2.0

        # 创建固定尺寸画布：和背景图原始尺寸完全一致
        final_canvas = QImage(bg_original_w, bg_original_h, QImage.Format_ARGB32)
        final_canvas.fill(Qt.transparent)

        # 反向偏移绘图，越界自动补透明像素，不限制边界、中心点无偏移
        painter = QPainter(final_canvas)
        painter.drawPixmap(-final_crop_x, -final_crop_y, scaled_fluo)
        painter.end()

        aligned_fluo = QPixmap.fromImage(final_canvas)
        aligned_fluo.setDevicePixelRatio(device_pixel_ratio)
        if aligned_fluo.isNull():
            return QPixmap()
        aligned_fluo.save("D:\\ToBeRead\\PIBB\\20260612mito_fluor_CBItest\\20260610_mito_red\\aligned_fluo.jpg", "JPG", 100)
        """# ====================== 生成归一化融合图像，完全匹配原有绘制逻辑 ======================
        # 创建与背景图尺寸完全一致的透明画布
        final_image = QImage(bg_original_w, bg_original_h, QImage.Format_ARGB32_Premultiplied)
        final_image.fill(Qt.transparent)

        # 初始化画笔，设置无损渲染提示和透明度叠加逻辑
        painter = QPainter(final_image)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.Antialiasing, True)
        # 采用 SourceOver 叠加模式，完美还原原有透明度显示效果
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        # 绘制对齐后的荧光图，将其与背景图基准画布完全重合
        painter.drawImage(QPointF(0, 0), aligned_fluo)
        painter.end()

        # 转换为 QPixmap，适配原有绘制逻辑，同步高DPI设备像素比
        result_pixmap = QPixmap.fromImage(final_image)
        result_pixmap.setDevicePixelRatio(device_pixel_ratio)"""

        # ====================== 主动释放临时资源，最大化内存回收效率 ======================
        transformed_fluo.detach()
        first_cropped.detach()
        scaled_fluo.detach()
        #aligned_fluo.detach()
        #final_image.detach()
        print(f"crop down, memory released. aligned_fluo.size: {aligned_fluo.width()} x {aligned_fluo.height()}")

        return aligned_fluo

       


    def toggle_lock(self):
        """
        终极优化：归一化锁定+内存原图替换+彻底解决卡顿
        1. 锁定：生成同尺寸对齐归一化荧光图，**直接替换内存原始荧光图**，保存归一化原图文件
        2. 锁定后废弃所有实时矩阵变换，仅简单缩放平移，彻底根治卡顿
        3. 解锁：100%还原锁定前所有原始状态，无任何丢失、无偏差
        """
        self.is_locked = not self.is_locked

        if self.is_locked and self.image and self.bg_image:
            # ========== 锁定流程：全量快照 + 替换内存原图 + 保存归一化文件 ==========
            # 完整保存锁定前所有原始状态（解锁还原专用）
            self.lock_image_state = {
                'raw_image': self.image,
                'angle': self.angle,
                'scale': self.scale_spinbox.value(),
                'offset': self.image_offset,
                'bg_scale': self.bg_scale_spinbox.value(),
                'bg_offset': self.bg_offset,
                'bg_image': self.bg_image,
                'stretch_angle': self.stretch_angle_spinbox.value(),
                'stretch_factor': self.stretch_factor_spinbox.value(),
                'opacity': self.opacity,
            }

            # 生成【与背景图同尺寸、像素级完全对齐】的归一化荧光图
            self.normalized_fluo_image = self.create_normalized_fluo_image()

            # 核心优化：直接覆盖内存中的原始荧光图，锁定后无需任何矩阵运算
            #self.image = self.normalized_fluo_image
                    # 2. ========== 按公式缩放：最终图 = 归一化图 * 背景缩放 / 荧光缩放 ==========
            fluo_scale_ratio = self.scale_spinbox.value() / 100.0
            bg_scale_ratio = self.bg_scale_spinbox.value() / 100.0
            # 计算缩放系数
            target_scale = bg_scale_ratio / fluo_scale_ratio

            # 获取归一化图原始宽高
            norm_w = self.normalized_fluo_image.width()
            norm_h = self.normalized_fluo_image.height()
            # 计算目标尺寸
            target_w = norm_w * target_scale
            target_h = norm_h * target_scale

            # 执行缩放，赋值给 self.image
            self.image = self.normalized_fluo_image.scaled(
                int(target_w),
                int(target_h),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            # 计算精准联动缩放比例
            self.lock_ratio = self.scale_spinbox.value() / self.bg_scale_spinbox.value()
            # ========== 新增：锁定后偏移量置零 ==========
            self.image_offset = QPointF(0.0, 0.0)

            # 保存三类成品文件
            if self.image_path:
                base_path = os.path.dirname(self.image_path)
                image_name = os.path.splitext(os.path.basename(self.image_path))[0]
                # 1. 保存归一化对齐荧光原图（新增核心需求）
                self.normalized_fluo_image.save(os.path.join(base_path, f"{image_name}_normalized_fluo.jpg"), "JPEG", 100)
                # 2. 保存背景原图
                self.bg_image.save(os.path.join(base_path, f"{image_name}_TEM.jpg"), "JPEG", 100)
                # 3. 保存叠合对比效果图
                self.image_label.grab().save(os.path.join(base_path, f"{image_name}_combined.jpg"), "JPEG", 100)

            print("✅ 锁定成功：内存原图已归一化替换，坐标完全对齐，卡顿已修复")

        else:
            # ========== 解锁流程：无损还原所有原始状态 ==========
            if self.lock_image_state:
                # 还原原始未归一化荧光图
                self.image = self.lock_image_state['raw_image']
                self.angle = self.lock_image_state['angle']
                self.scale_spinbox.setValue(self.lock_image_state['scale'])
                self.image_offset = self.lock_image_state['offset']
                self.bg_image = self.lock_image_state['bg_image']
                self.bg_scale_spinbox.setValue(self.lock_image_state['bg_scale'])
                self.bg_offset = self.lock_image_state['bg_offset']
                self.rotate_spinbox.setValue(self.angle)

                # 还原所有拉伸、透明度参数
                self.stretch_angle_spinbox.setValue(self.lock_image_state['stretch_angle'])
                self.stretch_factor_spinbox.setValue(self.lock_image_state['stretch_factor'])
                self.opacity = self.lock_image_state['opacity']

                # 清空归一化缓存与锁定快照
                self.normalized_fluo_image = None
                self.lock_image_state = None
                print("✅ 解锁成功：完全恢复锁定前原始图像与参数状态")

        self.update_image()

    def update_image(self):
        self.image_label.repaint()
        combined_image = QImage(self.image_label.size(), QImage.Format_ARGB32)
        combined_image.fill(Qt.transparent)
        painter = QPainter(combined_image)

        # ---------- 绘制背景图 ----------
        if self.bg_image:
            bg_scale = self.bg_scale_spinbox.value() / 100
            scaled_bg = self.bg_image.scaled(
                int(self.bg_image.width() * bg_scale),
                int(self.bg_image.height() * bg_scale),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation               
            )    #Qt.SmoothTransformation
            bg_x = (self.image_label.width() - scaled_bg.width()) // 2 + self.bg_offset.x()
            bg_y = (self.image_label.height() - scaled_bg.height()) // 2 + self.bg_offset.y()
            painter.drawPixmap(bg_x, bg_y, scaled_bg)

            # 绘制椭圆标记点
            self.ellipse_width = self.IA_spinbox.value() * 10000 / (self.PS_spinbox.value()) * bg_scale
            self.ellipse_height = self.ellipse_width * self.config['ellipse_height_width_ratio']
            self.ellipse_angle = 90 - self.config['ellipse_angle']

            pen = QPen(Qt.white, 2)
            painter.setPen(pen)
            for (ox, oy) in self.points:
                sx = int(ox * scaled_bg.width() / self.bg_image.width()) + bg_x
                sy = int(oy * scaled_bg.height() / self.bg_image.height()) + bg_y
                painter.save()
                painter.translate(sx, sy)
                painter.rotate(self.ellipse_angle)
                painter.drawEllipse(-self.ellipse_width//2, -self.ellipse_height//2, self.ellipse_width, self.ellipse_height)
                painter.restore()

        # ---------- 绘制荧光图：锁定极致优化逻辑 ----------
        if self.image:
            if self.is_locked:
                # 锁定状态：图像已是归一化同尺寸，无任何矩阵运算，极致流畅
                scale = self.scale_spinbox.value() / 100
                scaled_fluo = self.image.scaled(
                    int(self.image.width() * scale),
                    int(self.image.height() * scale),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                # 双图偏移完全同步，绝对像素对齐
                x = (self.image_label.width() - scaled_fluo.width()) // 2 + self.image_offset.x()
                y = (self.image_label.height() - scaled_fluo.height()) // 2 + self.image_offset.y()

            else:
                # 解锁状态：正常执行全套变换逻辑
                stretch_angle = self.stretch_angle_spinbox.value()
                stretch_factor = self.stretch_factor_spinbox.value()
                scale = self.scale_spinbox.value() / 100

                # 合并所有变换，减少精度损失
                transform = QTransform()
                """transform.translate(self.image.width()/2, self.image.height()/2)
                transform.rotate(stretch_angle)
                transform.scale(stretch_factor, 1.0)
                transform.rotate(-stretch_angle)
                transform.rotate(self.angle)
                transform.scale(scale, scale)
                transform.translate(-self.image.width()/2, -self.image.height()/2)"""


                transform.translate(self.image.width()/2, self.image.height()/2)
                
                # 先全局旋转（整个人旋转）
                transform.rotate(self.angle)
                # 再执行拉伸（基于原图未旋转坐标系拉伸，高矮固定）
                transform.rotate(stretch_angle)
                transform.scale(stretch_factor, 1.0)
                transform.rotate(-stretch_angle)
                transform.scale(scale, scale)
                transform.translate(-self.image.width()/2, -self.image.height()/2)



                scaled_fluo = self.image.transformed(transform, Qt.SmoothTransformation)
                x = (self.image_label.width() - scaled_fluo.width()) // 2 + self.image_offset.x()
                y = (self.image_label.height() - scaled_fluo.height()) // 2 + self.image_offset.y()

            # 统一透明度绘制
            opacity_img = QImage(scaled_fluo.size(), QImage.Format_ARGB32)
            opacity_img.fill(Qt.transparent)
            op_painter = QPainter(opacity_img)
            op_painter.setOpacity(self.opacity / 100)
            op_painter.drawPixmap(0, 0, scaled_fluo)
            op_painter.end()

            painter.drawPixmap(x, y, QPixmap.fromImage(opacity_img))

        painter.end()
        self.image_label.setPixmap(QPixmap.fromImage(combined_image))

    def rotate_image(self, value):
        self.angle = value
        self.update_image()

    def update_opacity(self, value):
        self.opacity = value
        self.update_image()

    def update_scale(self, value):
        # 锁定状态精准联动缩放
        if self.is_locked and self.lock_image_state:
            self.bg_scale_spinbox.setValue(value / self.lock_ratio)
        self.scale_spinbox.setValue(value)
        self.update_image()

    def update_bg_scale(self, value):
        # 锁定状态精准联动缩放
        if self.is_locked and self.lock_image_state:
            self.scale_spinbox.setValue(value * self.lock_ratio)
        self.bg_scale_spinbox.setValue(value)
        self.update_image()

    def toggle_transparency(self):
        if self.is_transparent:
            self.opacity = self.previous_opacity
        else:
            self.previous_opacity = self.opacity
            self.opacity = 0
        self.is_transparent = not self.is_transparent
        self.update_image()

    def toggle_add_points_mode(self):
        self.add_points_mode = not self.add_points_mode
        if self.add_points_mode:
            self.uniqueID = GetUniqueID()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.mouse_moved = False
            self.initial_click_pos = event.pos()
            
            if self.control_widget.underMouse() and self.top_layout.geometry().contains(event.pos()):
                self.old_pos = event.globalPos()
                self.dragging = True
            elif not self.control_widget.underMouse():
                self.dragging = True
                self.last_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() & Qt.LeftButton:
            if self.initial_click_pos:
                delta = event.pos() - self.initial_click_pos
                if delta.manhattanLength() > self.drag_threshold:
                    self.mouse_moved = True
            
            if self.old_pos:
                # 拖动窗口
                delta = event.globalPos() - self.old_pos
                self.move(self.pos() + delta)
                self.old_pos = event.globalPos()
            else:
                # 锁定状态：双图位移完全同步，绝对对齐
                delta = event.globalPos() - self.last_pos
                move_step = QPointF(delta.x(), delta.y())
                self.image_offset += move_step
                if self.is_locked:
                    self.bg_offset += move_step
                self.last_pos = event.globalPos()
            
            self.update_image()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
            self.old_pos = None
            
            if (self.add_points_mode and self.bg_image 
                and not self.mouse_moved and self.initial_click_pos):
                
                scaled_bg = self.bg_image.scaled(
                    int(self.bg_image.width() * self.bg_scale_spinbox.value() / 100),
                    int(self.bg_image.height() * self.bg_scale_spinbox.value() / 100),
                    Qt.KeepAspectRatio
                )
                bg_x = (self.image_label.width() - scaled_bg.width()) // 2 + self.bg_offset.x()
                bg_y = (self.image_label.height() - scaled_bg.height()) // 2 + self.bg_offset.y()
                click_x = self.initial_click_pos.x() - bg_x
                click_y = self.initial_click_pos.y() - bg_y - self.control_widget.height()
                
                if 0 <= click_x < scaled_bg.width() and 0 <= click_y < scaled_bg.height():
                    ox = int(click_x * self.bg_image.width() / scaled_bg.width())
                    oy = int(click_y * self.bg_image.height() / scaled_bg.height())
                    print(f"点击位置: ({ox}, {oy})")
                    self.points.append((ox, oy))
                    self.update_image()
                    AddPoint(ox, oy, self.uniqueID)
            
            self.initial_click_pos = None

    def wheelEvent(self, event):
        num_steps = event.angleDelta().y() / 120
        new_scale = self.scale_spinbox.value() + num_steps * 20
        new_scale = max(10, min(5000, new_scale))
        self.update_scale(new_scale)

    def on_flip_changed(self, index):
        """处理flip状态变化"""
        self.flip_image = index
        if self.image_path:
            self.load_image()


if __name__ == "__main__":
    # 开启高DPI适配，消除高分屏偏移
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)

    app = QApplication(sys.argv)
    # 设置全局字体
    font = QFont()
    font.setFamily("微软雅黑")
    font.setPointSize(10)
    app.setFont(font)

    viewer = TransparentImageViewer()
    viewer.setWindowTitle("透明图片对齐查看器（终极无卡顿归一化版）")
    viewer.move(100, 100)
    # 保留无边框置顶，不影响对齐精度
    viewer.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
    viewer.setAttribute(Qt.WA_TranslucentBackground)
    viewer.show()
    sys.exit(app.exec_())
