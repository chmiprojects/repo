import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox,QLabel
from PyQt5.uic import loadUi
from PyQt5.QtCore import QTimer, QElapsedTimer, QThread, pyqtSignal,Qt
import file_rc
from pin_init import *
from api_credentials import *
import pygame
import time
import requests
import subprocess
import signal
c=0
GPIO.cleanup()
GPIO.setmode(GPIO.BCM)

#output pin
GPIO.setup([door_lock_pin, dropping_cylinder_pin, pet_bottle_cylinder_pin, glass_bottle_cylinder_pin], GPIO.OUT)

# Set GPIO pins as input  cmt
GPIO.setup([ir2,dropping_cylinder_sensor_reverse_pin, dropping_cylinder_sensor_forward_pin, 
            pet_bottle_cylinder_sensor_reverse_pin_1, pet_bottle_cylinder_sensor_reverse_pin_2,
            glass_bottle_cylinder_sensor_reverse_pin, glass_bottle_cylinder_sensor_forward_pin,
            IR_sensor_pin, metal_detector_sensor_pin,glass_sensor], GPIO.IN,pull_up_down=GPIO.PUD_DOWN)

reset()
# Load models
class YoloThread(QThread):
    
    detection_signal = pyqtSignal(str)

    def __init__(self,headers,bottle_type):## Changed for glass logic
        super().__init__()
        self.headers = headers
        
        self.bottle_type=bottle_type## Added for glass logic
        
        self.lang = "eng"
        self.bottle=False
        from ultralytics import YOLO
        self.model = YOLO("yolov8m-cls.pt")
        reset()
        
##    def is_bottle(self, clss,cls_names):
##        detected_obj = ""
##        for cl in clss:
##            detected_obj = cls_names[int(cl)]
##            if detected_obj in ["bottle", "bottles", "vase"]:
##                return "bottle"
##        return detected_obj


    def run(self):
        print("in run")
        while True:
            print("frame capture")
            results = self.model.predict(stream=True, show=False, source=0)
            print("results taken")
            for result in results:
                probs = result.probs.data.tolist()
                classes = result.names
                detected=None

                glass_indicators = {
                    440: "Beer bottle",
                    901: "Whiskey jug",
                    907: "Wine bottle",
                    441: "Beer glass",  # Added beer glass
                    438: "Beaker",
                    966: "Red Wine",
                    737: "Pop Bottle"
                }
                plastic_indicators = {898: "Water bottle", 899: "Water jug"}
               
                # Get top 5 probabilities and their indices for better diagnosis
                top_5_indices = sorted(range(len(probs)), key=lambda i: probs[i], reverse=True)[:5]
               
                water_bottle_prob = max(probs[898], probs[899])
                max_glass_prob = max([probs[i] for i in glass_indicators], default=0)
 
                for idx in top_5_indices:
                    if idx in glass_indicators and probs[idx] > 0.1:
                        detected="glass"
               
                # If no glass container with higher probability than water bottle, check for plastic bottles
                for idx in top_5_indices:
                    if idx in plastic_indicators and probs[idx] > 0.2:
                        detected="pet"
                print(detected)
                bottle_detected=False

                metal_detected=""
                something_detected=""
                bottle_detected=""
                glass_detected=""

                is_ir_active = GPIO.input(IR_sensor_pin)
                is_metal_active = GPIO.input(metal_detector_sensor_pin)
                if(is_metal_active):
                    time.sleep(2)
                    is_metal_active = GPIO.input(metal_detector_sensor_pin)
                    
                
                is_ir2_active = GPIO.input(ir2)
                if is_ir_active==1:
                    something_detected=True
                           
                if is_metal_active==1:
                    metal_detected=True
                print("############################")
                print(f"Sensor Status :: camera={detected}//ir={something_detected}//metal={metal_detected}")
                print("############################")
                something_detected=True
                if something_detected==True and metal_detected==True:
                    print("something and metal")
                    self.bottle=True
                    metalDetected()
                    try:
                        print("metal")
                        data_bottle = {
                            "material_type": "can",
                            "quantity": "1"
                            }
                        response = requests.post(api_url_add_bottle, headers=self.headers, json=data_bottle)
                        response.raise_for_status()
                        add_bottle_response = response.json()
                        print("Metal Bottles added successfully!")
                    except:
                        pass

                if something_detected==True and detected=="pet":
#                    print("somethine detected")  cmt
                    self.bottle=True
                    petDetected()
                    try:
                        print("pet")
                        data_bottle = {
                            "material_type": "plastic",
                            "quantity": "1"
                            }
                        response = requests.post(api_url_add_bottle, headers=self.headers, json=data_bottle)
                        response.raise_for_status()  # Raise exception for non-200 status codes cmt
                        add_bottle_response = response.json()
                        print("Pet Bottles added successfully!")
                    except:
                        pass

                if something_detected==True and detected=="glass":
                #if self.bottle_type=="glass" and detected=="pet":
                    print("glass Detected")
                    glassDetected()
                    self.bottle=True
                    
                    self.bottle_type=None  ## Added for glass logic
                    
                    try:
                        print("glass")
                        data_bottle = {
                            "material_type": "glass",
                            "quantity": "1"
                            }
                        response = requests.post(api_url_add_bottle, headers=self.headers, json=data_bottle)
                        response.raise_for_status()  # Raise exception for non-200 status codes  cmt
                        add_bottle_response = response.json()
                        print("Glass Bottles added successfully!")
                    except:
                        pass
                        ############################################

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.ui = loadUi('main.ui',self)

        #self.ui = ui
        pygame.mixer.init()
        pygame.mixer.music.load("/home/rpiuser/configurations/soothing.mp3")
        pygame.mixer.music.play(loops=-1)

                #### Timer Logic#### cmt
        self.current_page = "home"
        self.elapsed_timer = QElapsedTimer()
        self.elapsed_timer.start()




        ### Timer update

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_timer)
        self.timer.start(1000)  # Update every 1 second cmt
        self.remaining_time = 30

        self.timerForBottle = QTimer()
        self.timerForBottle.timeout.connect(self.update_screen)
        self.timerForBottle.start(500)  # Update every 1 second cmt

        
        
        self.ui.stackedWidget.setCurrentWidget(self.ui.welcomePage)
        self.lang = "eng"

        # Timer for inactivity
        self.current_page = "home"
        self.elapsed_timer = QElapsedTimer()
        self.elapsed_timer.start()
        self.updated_headers = None
        self.bottle_type=None

        # Start YOLO thread
        self.yolo_thread = YoloThread(self.updated_headers,self.bottle_type)
        self.yolo_thread.detection_signal.connect(self.yolo_thread.run)
        self.yolo_thread.start()


        self.ui.englishButton.clicked.connect(self.enterNumberEngFunct)
        self.ui.hindiButton.clicked.connect(self.enterNumberHindiFunct)
        self.ui.num_1.clicked.connect(self.num_1_clicked)
        self.ui.num_2.clicked.connect(self.num_2_clicked)
        self.ui.num_3.clicked.connect(self.num_3_clicked)
        self.ui.num_4.clicked.connect(self.num_4_clicked)
        self.ui.num_5.clicked.connect(self.num_5_clicked)
        self.ui.num_6.clicked.connect(self.num_6_clicked)
        self.ui.num_7.clicked.connect(self.num_7_clicked)
        self.ui.num_8.clicked.connect(self.num_8_clicked)
        self.ui.num_9.clicked.connect(self.num_9_clicked)
        self.ui.num_0.clicked.connect(self.num_0_clicked)
        self.ui.num_ok.clicked.connect(self.num_ok_clicked)
        self.ui.num_del.clicked.connect(self.num_del_clicked)
        self.ui.num_1_hindi.clicked.connect(self.num_1_hindi_clicked)
        self.ui.num_2_hindi.clicked.connect(self.num_2_hindi_clicked)
        self.ui.num_3_hindi.clicked.connect(self.num_3_hindi_clicked)
        self.ui.num_4_hindi.clicked.connect(self.num_4_hindi_clicked)
        self.ui.num_5_hindi.clicked.connect(self.num_5_hindi_clicked)
        self.ui.num_6_hindi.clicked.connect(self.num_6_hindi_clicked)
        self.ui.num_7_hindi.clicked.connect(self.num_7_hindi_clicked)
        self.ui.num_8_hindi.clicked.connect(self.num_8_hindi_clicked)
        self.ui.num_9_hindi.clicked.connect(self.num_9_hindi_clicked)
        self.ui.num_0_hindi.clicked.connect(self.num_0_hindi_clicked)
        self.ui.num_ok_hindi.clicked.connect(self.num_ok_hindi_clicked)
        self.ui.num_del_hindi.clicked.connect(self.num_del_hindi_clicked)
        self.ui.plasticBottleButton.clicked.connect(self.plasticBottleButtonClicked)
        self.ui.canButton.clicked.connect(self.canButtonClicked)
        self.ui.glassButton.clicked.connect(self.glassButtonClicked)
        self.ui.plasticButtonHindi.clicked.connect(self.plasticBottleButtonHindiClicked)
        self.ui.canButtonHindi.clicked.connect(self.canButtonHindiClicked)
        self.ui.glassButtonHindi.clicked.connect(self.glassButtonHindiClicked)
        self.ui.homeButton.clicked.connect(self.homeButtonClicked)
        self.ui.homeButton_1.clicked.connect(self.homeButtonClicked)
        self.ui.homeButton_2.clicked.connect(self.homeButtonClicked)
        self.ui.homeButton_3.clicked.connect(self.homeButtonClicked)
        self.ui.homeButton_4.clicked.connect(self.homeButtonClicked)
        self.ui.homeButton_5.clicked.connect(self.homeButtonClicked)
        self.ui.yesButton.clicked.connect(self.yesButtonClicked)
        self.ui.noButton.clicked.connect(self.noButtonClicked)
        self.ui.yesButtonHindi.clicked.connect(self.yesButtonHindiClicked)
        self.ui.noButtonHindi.clicked.connect(self.noButtonHindiClicked)
        self.showFullScreen()
    def update_timer(self):
        
        if(self.ui.stackedWidget.currentIndex()==4 or self.ui.stackedWidget.currentIndex()==5):
            self.remaining_time -= 1
        if self.remaining_time == 0:
            reset()
            #self.timer.stop()
            self.remaining_time=30
            if(self.ui.stackedWidget.currentIndex()==4):
                self.ui.stackedWidget.setCurrentWidget(self.ui.trashValidated)
            if (self.ui.stackedWidget.currentIndex()==5):
                self.ui.stackedWidget.setCurrentWidget(self.ui.trashValidatedHindi)
        else:
            
            self.timer_value.setText(str(self.remaining_time))
            self.timer_value_hindi.setText(str(self.remaining_time))

    def update_screen(self):
        if(self.yolo_thread.bottle==True):
            
            self.yolo_thread.bottle=False
            print("screen changed")
            if(main_window.ui.stackedWidget.currentIndex()==4):
                main_window.ui.stackedWidget.setCurrentWidget(main_window.ui.trashValidated)
                main_window.remaining_time = 30
                

            if(main_window.ui.stackedWidget.currentIndex()==5):
                
                main_window.ui.stackedWidget.setCurrentWidget(main_window.ui.trashValidatedHindi)
                

                
                main_window.remaining_time = 30

    def enterNumberEngFunct(self):
        self.lang = "eng"
        self.ui.stackedWidget.setCurrentWidget(self.ui.enterNumberEng)
        self.current_page = "enterNumberEng"
        self.elapsed_timer.restart()
        
    def enterNumberHindiFunct(self):
        self.lang = "hindi"
        self.ui.stackedWidget.setCurrentWidget(self.ui.enterNumberHindi)
        self.current_page = "enterNumberHindi"
        self.elapsed_timer.restart()

    def num_1_clicked(self):
        self.ui.inputEnglish.insert("1")
    def num_2_clicked(self):
        self.ui.inputEnglish.insert("2")
    def num_3_clicked(self):
        self.ui.inputEnglish.insert("3")
    def num_4_clicked(self):
        self.ui.inputEnglish.insert("4")
    def num_5_clicked(self):
        self.ui.inputEnglish.insert("5")
    def num_6_clicked(self):
        self.ui.inputEnglish.insert("6")
    def num_7_clicked(self):
        self.ui.inputEnglish.insert("7")
    def num_8_clicked(self):
        self.ui.inputEnglish.insert("8")
    def num_9_clicked(self):
        self.ui.inputEnglish.insert("9")
    def num_0_clicked(self):
        self.ui.inputEnglish.insert("0")
        
    def num_ok_clicked(self):

            try:
                self.currentTextEng = self.ui.inputEnglish.text()
                self.ui.inputEnglish.clear()
                if len(self.currentTextEng) == 10:
                    self.ui.stackedWidget.setCurrentWidget(self.ui.bottleSelection)

                    self.data_login = {"mobilenum": self.currentTextEng}
                    response = requests.post(api_url_login, headers=headers, json=self.data_login)
                    response.raise_for_status()
                    login_response = response.json()
                    auth_token = login_response["data"]["authtoken"]
                    headers["Authorization"] = f"Bearer {auth_token}"
                    self.updated_headers = headers

                    # Update the headers in the YoloThread
                    self.yolo_thread.headers = self.updated_headers

                    self.current_page = "bottleSelection"
                    self.elapsed_timer.restart()
                else:
                    QMessageBox.warning(self, "Warning", "Please enter a correct number")

            except:
                QMessageBox.warning(self, "Warning", "No Internetें")

    def num_1_hindi_clicked(self):
        self.ui.inputHindi.insert("1")
    def num_2_hindi_clicked(self):
        self.ui.inputHindi.insert("2")
    def num_3_hindi_clicked(self):
        self.ui.inputHindi.insert("3")
    def num_4_hindi_clicked(self):
        self.ui.inputHindi.insert("4")
    def num_5_hindi_clicked(self):
        self.ui.inputHindi.insert("5")
    def num_6_hindi_clicked(self):
        self.ui.inputHindi.insert("6")
    def num_7_hindi_clicked(self):
        self.ui.inputHindi.insert("7")
    def num_8_hindi_clicked(self):
        self.ui.inputHindi.insert("8")
    def num_9_hindi_clicked(self):
        self.ui.inputHindi.insert("9")
    def num_0_hindi_clicked(self):
        self.ui.inputHindi.insert("0")
    def num_ok_hindi_clicked(self):
     
        try:
            self.currentTextHindi = self.ui.inputHindi.text()
            self.ui.inputHindi.clear()

            if len(self.currentTextHindi) == 10:
                self.ui.stackedWidget.setCurrentWidget(self.ui.bottleSelectionHindi)
                self.data_login = {"mobilenum": self.currentTextHindi}
                response = requests.post(api_url_login, headers=headers, json=self.data_login)
                response.raise_for_status()
                login_response = response.json()
                auth_token = login_response["data"]["authtoken"]
                headers["Authorization"] = f"Bearer {auth_token}"
                self.updated_headers = headers

                # Update the headers in the YoloThread
                self.yolo_thread.headers = self.updated_headers
                self.current_page = "bottleSelectionHindi"
                self.elapsed_timer.restart()
            else:
                QMessageBox.warning(self, "Warning", "कृपया सही संख्या दर्ज करें")
        except Exception as e:
            QMessageBox.warning(self, "Warning", "कृपया सही संख्या दर्ज करें")
    def num_del_hindi_clicked(self):
        self.ui.inputHindi.backspace()

    def plasticBottleButtonClicked(self):
            
        GPIO.output(dropping_cylinder_pin, GPIO.HIGH)
        self.ui.stackedWidget.setCurrentWidget(self.ui.enterBottle)
        self.current_page = "enterBottle"
        self.elapsed_timer.restart()
    def canButtonClicked(self):
        GPIO.output(dropping_cylinder_pin, GPIO.HIGH)
        self.ui.stackedWidget.setCurrentWidget(self.ui.enterBottle)
        self.current_page = "enterBottle"
        self.elapsed_timer.restart()
    def glassButtonClicked(self):
        GPIO.output(dropping_cylinder_pin, GPIO.HIGH)

        
        self.bottle_type="glass"### Addsded for glass logic

        
        self.ui.stackedWidget.setCurrentWidget(self.ui.enterBottle)
        self.current_page = "enterBottle"
        self.elapsed_timer.restart()

    def plasticBottleButtonHindiClicked(self):
        GPIO.output(dropping_cylinder_pin, GPIO.HIGH)
        self.ui.stackedWidget.setCurrentWidget(self.ui.enterBottleHindi)
        self.current_page = "enterBottleHindi"
        self.elapsed_timer.restart()
    def canButtonHindiClicked(self):
        GPIO.output(dropping_cylinder_pin, GPIO.HIGH)
        self.ui.stackedWidget.setCurrentWidget(self.ui.enterBottleHindi)
        self.current_page = "enterBottleHindi"
        self.elapsed_timer.restart()
    def glassButtonHindiClicked(self):
        GPIO.output(dropping_cylinder_pin, GPIO.HIGH)
        self.ui.stackedWidget.setCurrentWidget(self.ui.enterBottleHindi)
        
        self.bottle_type="glass"## Added for glass logic
        
        self.current_page = "enterBottleHindi"
        self.elapsed_timer.restart()

    def num_del_clicked(self):
        self.ui.inputEnglish.backspace()

    def homeButtonClicked(self):
        self.ui.stackedWidget.setCurrentWidget(self.ui.welcomePage)
        self.current_page = "home"
        self.ui.inputEnglish.clear()
        self.ui.inputHindi.clear()
        self.elapsed_timer.restart()

    def yesButtonClicked(self):
        self.ui.stackedWidget.setCurrentWidget(self.ui.bottleSelection)
        self.current_page = "bottleSelection"
        self.elapsed_timer.restart()
    def noButtonClicked(self):
        self.ui.stackedWidget.setCurrentWidget(self.ui.welcomePage)
        self.current_page = "home"
        self.elapsed_timer.restart()
    def yesButtonHindiClicked(self):
        self.ui.stackedWidget.setCurrentWidget(self.ui.bottleSelectionHindi)
        self.current_page = "bottleSelectionHindi"
        self.elapsed_timer.restart()
    def noButtonHindiClicked(self):
        self.ui.stackedWidget.setCurrentWidget(self.ui.welcomePage)
        self.current_page = "home"
        self.elapsed_timer.restart()

    def handle_inactivity(self):
        if self.current_page != "home" and self.elapsed_timer.elapsed() >= 80000:
            self.ui.stackedWidget.setCurrentWidget(self.ui.welcomePage)
            self.ui.inputEnglish.clear()
            self.ui.inputHindi.clear()
            self.elapsed_timer.restart()

if __name__ == "__main__":
    try:

        app = QApplication(sys.argv)
        main_window = MainWindow()
        main_window.show()
        timer = QTimer()
        timer.timeout.connect(main_window.handle_inactivity)
        timer.start(1000)
        
        sys.exit(app.exec_())
    except:
        print("error detected")



