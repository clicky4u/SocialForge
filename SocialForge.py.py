from cmath import e
import csv
import ctypes
from bs4 import BeautifulSoup
import imaplib
import logging
import re
import string
import sys
import threading
import time
import os
import webbrowser
from PyQt5.QtGui import QPixmap
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QCheckBox ,QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QComboBox, QCheckBox, QWidget, QAction, QMenu
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import random
import names
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtWidgets import QDialog ,QLabel
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtWidgets import QFileDialog, QAction, QMenu, QMessageBox, QTableWidgetItem

class Worker(QtCore.QObject):
    finished = QtCore.pyqtSignal()
    progress = QtCore.pyqtSignal(str, str, str, str, str, str, str, str, str,str)

    def __init__(self, thread_id, names_list, delay, stop_after, gender_option, random_phone, use_random_password,
                 custom_password, email_queue, lock, account_no_verify, account_fullverify, name_source, stop_flag=None, output_lock=None):
        super().__init__()
        self.thread_id = thread_id
        self.names_list = names_list
        self.delay = delay
        self.stop_after = stop_after
        self._is_running = True
        self.gender_option = gender_option
        self.random_phone = random_phone
        self.use_random_password = use_random_password
        self.custom_password = custom_password
        self.email_queue = email_queue  # Shared email queue
        self.lock = lock  # Thread-safe lock
        self.account_no_verify = account_no_verify  # Checkbox state
        self.account_fullverify = account_fullverify  # Checkbox state
        self.stop_flag = stop_flag if stop_flag else threading.Event()  # Use provided stop_flag or default Event
        self.name_source = name_source  # Store name_source
        self.used_codes = set()
        self.output_lock = threading.Lock()
        self.output_lock = output_lock


    def run(self):
        for i in range(self.stop_after):
            if self.stop_flag.is_set():  # Check the stop flag
                logging.info("Stop flag set. Stopping worker.")
                break

            self.register_account()
            time.sleep(self.delay)

        self.finished.emit()



    def get_verification_code(self, email, passmail):
        base_email = email.split('+')[0] + '@' + email.split('@')[-1]
        print(f"Using base email: {base_email} and password: {passmail}")
        try:
            # Connect to Yandex IMAP server
            mail = imaplib.IMAP4_SSL("imap.yandex.com")
            mail.login(base_email, passmail)
            
            # Select only the Spam folder
            mail.select("Spam")
            status, messages = mail.search(None, '(UNSEEN)')
            if status != "OK" or not messages[0]:
                print("No unread emails found in the Spam folder.")
                return None
            
            # Get the list of email IDs
            email_ids = messages[0].split()
            if not email_ids:
                print("No new emails found in the Spam folder.")
                return None
            
            # Limit to the last 20 unread emails
            email_ids = email_ids[-20:]  # Process only the latest 20 emails
            print(f"Found {len(email_ids)} unread emails in the Spam folder. Processing them...")
            
            # Iterate through emails in reverse order (newest first)
            for email_id in reversed(email_ids):
                status, msg_data = mail.fetch(email_id, "(RFC822)")
                if status != "OK":
                    continue
                
                # Parse the email content
                try:
                    raw_email = msg_data[0][1].decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        raw_email = msg_data[0][1].decode("iso-8859-1")  # Fallback encoding
                    except Exception as e:
                        print(f"Failed to decode email content: {e}")
                        continue
                
                # Use BeautifulSoup to extract plain text from HTML emails
                soup = BeautifulSoup(raw_email, "html.parser")
                plain_text = soup.get_text(separator="\n").strip()
                plain_text = " ".join(plain_text.split())
                print(f"Parsed plain text email content:\n{plain_text}")
                
                # Extract the recipient email address
                recipient_match = re.search(r"(?:This message was sent to|Recipient:)\s+([^\s@]+@[^\s@]+\.[^\s@]+)", plain_text)
                if recipient_match:
                    recipient_email = recipient_match.group(1).strip('.')
                    print(f"Recipient email extracted: {recipient_email}")
                    
                    # Ensure the recipient email matches the registered email
                    if recipient_email.split('+')[0] != email.split('+')[0]:
                        print(f"Email mismatch: Expected {email}, got {recipient_email}. Skipping this email.")
                        continue  # Skip to the next email
                    
                    # Extract the verification code using regex
                    code_match = re.search(r"FB-(\d{5})", plain_text)  # Captures the numeric part after FB-
                    if code_match:
                        verification_code = code_match.group(1)  # Extract only the numeric part
                        
                        # Check if the code has already been used
                        if verification_code in self.used_codes:
                            print(f"Verification code {verification_code} already used. Skipping.")
                            continue
                        
                        print(f"Verification code extracted: {verification_code}")
                        
                        # Mark the email as read and delete it
                        mail.store(email_id, '+FLAGS', '\\Seen \\Deleted')
                        mail.expunge()
                        
                        # Add the code to the used_codes set
                        self.used_codes.add(verification_code)
                        return verification_code
                    else:
                        print("Verification code not found in the email.")
                        continue  # Skip to the next email
                else:
                    print("Recipient email not found in the email body.")
                    continue  # Skip to the next email
            
            # If no matching email is found
            print("No matching email found in the Spam folder.")
            return None
        except imaplib.IMAP4.error as e:
            print(f"IMAP login failed: {e}")
            return None
        except Exception as e:
            print(f"Error fetching verification code: {e}")
            return None



    def register_account(self):
        """
        Simulates the Facebook account registration process.
        Handles form filling, email/phone verification, and status updates.
        """
        # Check if the stop flag is set before proceeding
        if self.stop_flag.is_set():
            logging.info("Stopping registration process.")
            return

        # Configure Chrome WebDriver options
        options = ChromeOptions()
        options.add_argument("--user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_1 like Mac OS X) AppleWebKit/603.1.30 (KHTML, like Gecko) Version/10.0 Mobile/14E304 Safari/602.1")
        options.add_argument("--window-size=250,430")

        # Define the number of windows per row for multi-threading layout
        max_columns = 8
        window_width = 236  # Width of the browser window
        window_height = 425  # Height of the browser window
        screen_width = 1920  # Screen width (adjust to your resolution)
        screen_height = 1080  # Screen height (adjust to your resolution)

        # Calculate the window's position based on the thread index
        row = self.thread_id // max_columns
        column = self.thread_id % max_columns
        x_position = min(column * window_width, screen_width - window_width)
        y_position = min(row * window_height, screen_height - window_height) 

        # Add the --window-position argument to set the initial position
        options.add_argument(f"--window-position={x_position},{y_position}")

        # Add the --app argument to open the app in standalone mode
        options.add_argument("--app=https://m.facebook.com/reg/")

        # Specify the path to the ChromeDriver executable
        driver_path = ".\\driver\\chromedriver.exe"
        service = Service(driver_path)

        # Introduce a delay before initializing the WebDriver for this thread
        time.sleep(self.thread_id * 1.5)  # Delay increases with thread_id (e.g., 1.5 seconds per thread)

        # Initialize the Chrome WebDriver with the specified options
        driver = webdriver.Chrome(service=service, options=options)


        # Safely get a unique email from the shared queue
        with self.lock:
            if not self.email_queue:
                print(f"No more emails available for thread {self.thread_id}. Stopping.")
                driver.quit()
                return
            email, passmail = self.email_queue.pop(0)  # Assign and remove the email-password pair

        print(f"Thread {self.thread_id} using email: {email} and password: {passmail}")

        try:
            # Generate first and last names based on the selected radio option
            if self.name_source == "Random":
                firstname = names.get_first_name()
                lastname = names.get_last_name()
            elif self.name_source == "English":
                firstname = names.get_first_name()
                lastname = names.get_last_name()
            elif self.name_source == "Thai":
                thai_first_names = [
                    "สมชาย", "ธนภัทร", "สุรชัย", "ปกรณ์", "พิชญ์",
                    "อนุชา", "วิทยา", "จิรายุ", "ก้องภพ", "ศุภชัย",
                    "ณัฐวุฒิ", "เอกชัย", "กิตติพงษ์", "พีรพล", "ชาญชัย",
                    "นราธิป", "อรรถพล", "พงศกร", "ปรีชา", "จารุวัฒน์",
                    "อธิชาติ", "วรพล", "วัฒนชัย", "ชลธิศ", "ธีรพล",
                    "สรวิชญ์", "ปรัชญา", "พีรวิชญ์", "ภาณุวัฒน์", "ภูมิพัฒน์",
                    "ธีรเดช", "เกรียงไกร", "ยุทธนา", "สมบัติ", "สันติ",
                    "พิชัย", "ณรงค์", "กิตติ", "วรวิทย์", "เจตน์",
                    "ภาคภูมิ", "พงษ์พิพัฒน์", "ณัฐพล", "วีระ", "มงคล",
                    "ปรีดา", "พิชิต", "วชิรวิทย์", "ทรงพล", "สุเมธ",
                    "ดนัย", "จตุพล", "นพดล", "ทรงศักดิ์", "สมพร",
                    "ภัทรพล", "อุดม", "อภิชาติ", "เกียรติศักดิ์", "ประยุทธ",
                    "วิชิต", "อิทธิพล", "เจษฎา", "ชนินทร์", "ณัฐกิตติ์",
                    "อาคม", "สุทธิเกียรติ", "นรินทร์", "ทศพล", "วิโรจน์",
                    "ปรเมศ", "ธนกฤต", "รัชพล", "รัฐพล", "ชวลิต",
                    "ณัฐดนัย", "รังสรรค์", "ดนุสรณ์", "วรศักดิ์", "พงศ์ศิริ",
                    "ธีรยุทธ", "วิชัย", "อนันต์", "วิทยา", "ศักดิ์ชัย",
                    "อานนท์", "ณัฐนนท์", "พิเชษฐ์", "วรวุฒิ", "ปรัชญา",
                    "จิรวัฒน์", "เจตนิพัทธ์", "ภูมิใจ", "กฤษดา", "สันติสุข",
                    "ศราวุฒิ", "เกียรติ", "อธิวัฒน์", "สุชาติ", "ปิยะ"
                ]
                thai_last_names = [
                    "ใจดี", "ศรีสวัสดิ์", "บุญช่วย", "วิเศษ", "มณีรัตน์",
                    "เจริญสุข", "ประเสริฐศรี", "สุขเกษม", "ทองดี", "รัตนโชติ",
                    "สุขสันต์", "กาญจนเกตุ", "ชัยมงคล", "พงษ์ไพบูลย์", "ทรงธรรม",
                    "วัฒนกุล", "สมบูรณ์", "ธนโชติ", "กัลยาณมิตร", "วิจิตรเกษม",
                    "ทวีสุข", "เจริญศรี", "พิพัฒน์พงศ์", "สิริกาญจน์", "รุ่งเรือง",
                    "บุญญโชติ", "สุทธิวัฒน์", "อัครเดช", "อินทราวุธ", "ธรรมรักษ์",
                    "กิตติวัฒน์", "รัตนากร", "ศิริโชค", "ณรงค์ศักดิ์", "สุวรรณ",
                    "อินทรศักดิ์", "ปรีดาพัฒน์", "พูนทรัพย์", "ศิริพร", "จิรโชติ",
                    "วิริยะกุล", "บุญยง", "เศรษฐกิจ", "อัศวิน", "ทองสุข",
                    "วรธรรม", "เจริญรุ่งเรือง", "สิทธิโชค", "เพชรรัตน์", "ประเสริฐ",
                    "ชนะชัย", "ศิริชัย", "บุญรอด", "รัตนาวดี", "วรากร",
                    "วิไลจิตร", "รุ่งเรืองศรี", "อินทรโชติ", "เกษมสุข", "ชาตรีกุล",
                    "ศุภมิตร", "ธรรมสุจริต", "อภิรักษ์", "พัฒนโชติ", "สุทธากร",
                    "อรุณศรี", "กิตติกุล", "วิเศษสุข", "บุญญาภิรมย์", "เศรษฐกิจ",
                    "เจริญเกียรติ", "ปรีชากุล", "อินทรมณี", "วิทยากุล", "เศรษฐีธรรม",
                    "ทองประเสริฐ", "ธรรมจารี", "พิชัยศรี", "จารุเกียรติ", "เกียรติชัย",
                    "รุ่งเกียรติ", "บุญกาญจน์", "ศุภกาญจน์", "อินทรรักษ์", "มณีรัตน์",
                    "วิริยะศรี", "รุ่งศิริ", "กัลยาณมิตร", "ณรงค์สุข", "วิเศษศรี",
                    "สุรโชติ", "ศรีสุข", "ทองวิเศษ", "อภิวัฒน์", "วิไลรักษ์"
                ]
                firstname = random.choice(thai_first_names)
                lastname = random.choice(thai_last_names)
            elif self.name_source == "Khmer":
                khmer_first_names = ["សុវណ្ណារិទ្ធ", "សារី", "វិច្ឆិកា", "សុភា", "ប៊ុនរឿន","សុផាត"]
                khmer_last_names = ["សុខ", "ខេមរា", "លី", "ចេង", "ឆែម","ចំរើន"]
                firstname = random.choice(khmer_first_names)
                lastname = random.choice(khmer_last_names)
            elif self.name_source == "Chinese":
                chinese_first_names = ["李", "王", "张", "刘", "陈"]
                chinese_last_names = ["伟", "芳", "娜", "敏", "静"]
                firstname = random.choice(chinese_first_names)
                lastname = random.choice(chinese_last_names)
            elif self.name_source == "File":
                # Load names from the text file using the existing method
                if self.names_list:
                    name = random.choice(self.names_list).split()
                    firstname = name[0]
                    lastname = name[1] if len(name) > 1 else ""
            else:
                # Default fallback to random English name
                firstname = names.get_first_name()
                lastname = names.get_last_name()

            full_name = f"{firstname} {lastname}"


            # Check for stop flag before proceeding further
            if self.stop_flag.is_set():
                logging.info("Stop flag detected. Exiting register_account.")
                driver.quit()
                return

            # Navigate to the Facebook registration page
            driver.get("https://m.facebook.com/reg/")

            # Fill in first name and last name fields
            driver.find_element(By.XPATH, '//*[@id="firstname_input"]').send_keys(firstname)
            driver.find_element(By.XPATH, '//*[@id="lastname_input"]').send_keys(lastname)
            time.sleep(260)
            print(f"Using name: {full_name}")
            # Click the "Next" button 3 times
            button_xpath = "/html/body/div[1]/div[1]/div[2]/div[2]/div/form/div[9]/div[2]/button[1]" 
            for _ in range(3):
                if self.stop_flag.is_set():
                    logging.info("Stop flag detected. Exiting register_account.")
                    driver.quit()
                    return
                btnNext = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, button_xpath))
                )
                btnNext.click()
                time.sleep(1)

            # Random Age Input
            random_age = random.randint(18, 59)
            print(f"Generated random age: {random_age}")
            age_xpath = "/html/body/div[1]/div[1]/div[2]/div[2]/div/form/div[4]/div[3]/div/div/div[1]/div[2]/div[2]/input" 
            age_input = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.XPATH, age_xpath))
            )
            age_input.send_keys(str(random_age))
            time.sleep(2)

            # Proceed to the next step
            btnNext = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, button_xpath))
            )
            btnNext.click()
            time.sleep(1)

            # Extract Birthdate Confirmation
            confirmation_message = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.XPATH, "//div[@class='_52je' and @data-sigil='age_step_confirmation_overlay_title']"))
            ).text
            date_match = re.search(r'(\w+ \d{1,2}, \d{4})', confirmation_message)
            birthdate = date_match.group(1) if date_match else "Unknown"
            print(f"Extracted Birthdate: {birthdate}")
            time.sleep(2)

            # Confirm Age
            btnok = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "/html/body/div[1]/div[1]/div[6]/div[1]/div/div[2]/div/div[3]/a[2]"))
            )
            btnok.click()
            time.sleep(2)

            if self.random_phone:
                # List of Cambodian mobile prefixes
                prefixes = [
                    "10", "11", "12", "13", "15", "16", "17", "18",
                    "60", "61", "66", "67", "68", "70", "71", "76",
                    "77", "78", "80", "81", "85", "86", "87", "88",
                    "89", "90", "92", "93", "95", "96", "97", "98"
                ]

                # Randomly select a prefix
                selected_prefix = random.choice(prefixes)

                # Generate 6 random digits for the local number
                random_digits = ''.join(random.choices("0123456789", k=6))

                # Format the phone number with spaces: +855 XX XXX XXX
                phone_number = f"+855 {selected_prefix} {random_digits[:3]} {random_digits[3:]}"
            else:
                # Read phone numbers from phone_number.txt
                try:
                    with open(".\\data\\phone_number.txt", "r", encoding="utf-8") as file:
                        phone_numbers = file.read().splitlines()  # Read all lines into a list
                        phone_numbers = [number.strip() for number in phone_numbers if number.strip()]  # Remove empty lines
                    if not phone_numbers:
                        raise ValueError("No valid phone numbers found in phone_number.txt")
                    phone_number = random.choice(phone_numbers)  # Randomly select a phone number
                    print(f"Using phone number from file: {phone_number}")
                except FileNotFoundError:
                    print("File phone_number.txt not found. Using default hardcoded phone number.")
                    phone_number = "+855 18 335 408"
                except ValueError as e:
                    print(f"Error: {e}. Using default hardcoded phone number.")
                    phone_number = "+855 18 335 408"


            phone_input_field = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.XPATH, "/html/body/div[1]/div[1]/div[2]/div[2]/div/form/div[5]/div[3]/div/div/div[1]/div[3]/div/input"))
            )
            phone_input_field.send_keys(phone_number)
            print(f"Phone Number: {phone_number}")
            time.sleep(2)

            # Proceed to the next step
            btnNext = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, button_xpath))
            )
            btnNext.click()
            time.sleep(1)

            # Gender Selection
            if self.gender_option == "Random":
                gender = random.choice(["Male", "Female"])
            elif self.gender_option == "Male":
                gender = "Male"
            elif self.gender_option == "Female":
                gender = "Female"

            if gender == "Male":
                male_gender_option = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "/html/body/div[1]/div[1]/div[2]/div[2]/div/form/div[6]/div[3]/div/div/div[3]/div/label[2]/div/div/div[1]"))
                )
                male_gender_option.click()
            elif gender == "Female":
                female_gender_option = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "/html/body/div[1]/div[1]/div[2]/div[2]/div/form/div[6]/div[3]/div/div/div[3]/div/label[1]/div/div/div[1]"))
                )
                female_gender_option.click()

            # Proceed to the next step
            btnNext = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, button_xpath))
            )
            btnNext.click()
            time.sleep(1)

            # Password Input
            if self.use_random_password:
                password = "".join(random.choices("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%&*+-;/=", k=15))
            else:
                password = self.custom_password

            password_input_field = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.XPATH, "/html/body/div[1]/div[1]/div[2]/div[2]/div/form/div[7]/div[3]/div/div/div[1]/div[2]/div/input"))
            )
            password_input_field.send_keys(password)
            time.sleep(2)

            # Submit the form
            btnSignup = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "/html/body/div[1]/div[1]/div[2]/div[2]/div/form/div[9]/div[2]/button[4]"))
            )
            btnSignup.click()
            time.sleep(20)



            # Check for successful registration
            try:
                success_message_xpath = "/html/body/div[1]/div/div[2]/div/div[1]/div/div/div[1]/span"
                WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.XPATH, success_message_xpath)))
                success_message = driver.find_element(By.XPATH, success_message_xpath).text
                if "Save your password now to make logging in even easier." in success_message:
                    print("Signup successful!")
                    status = "Successful"
                else:
                    print("Unexpected success message:", success_message)
                    status = "Fail"
                    uid = None
                    cookies = None
                    twofa = None
                    email = None
                    self.progress.emit(full_name, uid, password, phone_number, email, cookies, gender, birthdate, twofa, status)
                    driver.quit()
                    return
            except TimeoutException:
                # Registration failed due to timeout, check for checkpoint
                print("Registration failed: Success message not found. Checking for checkpoint...")
                try:
                    checkpoint_xpath = "/html/body/div[1]/div[1]/div[3]/div/div[1]/div/div/form/div/div/h1"
                    checkpoint_message = driver.find_element(By.XPATH, checkpoint_xpath).text
                    if "We need more information" in checkpoint_message:
                        print("Checkpoint detected: 'We need more information'. Registration failed.")
                        status = "Checkpoint"
                        uid = None
                        cookies = None
                        twofa = None
                        email = None
                        self.progress.emit(full_name, uid, password, phone_number, email, cookies, gender, birthdate, twofa, status)
                        driver.quit()
                        return
                except NoSuchElementException:
                    # Checkpoint not found, proceed to mark as failure
                    print("Checkpoint not found.")

                # If neither success nor checkpoint was detected
                uid = None
                cookies = None
                status = "Fail"
                twofa = None
                email = None
                self.progress.emit(full_name, uid, password, phone_number, email, cookies, gender, birthdate, twofa, status)
                driver.quit()
                return

            # Get Cookies and UID
            cookies_list = driver.get_cookies()
            uid = None
            cookies = ""
            for cookie in cookies_list:
                if cookie['name'] == 'c_user':
                    uid = cookie['value']
                cookies += f"{cookie['name']}={cookie['value']}; "
            cookies = cookies.strip("; ")

            # Update status based on UID
            if uid:
                print(f"UID from cookies: {uid}")
                status = "Successful"
            else:
                print("UID not found in cookies.")
                status = "Fail"

            # Checkbox Logic
            if self.account_no_verify:
                print("Account not verified. Quitting the driver.")
                twofa = None
                email = None
                self.progress.emit(full_name, uid, password, phone_number, email, cookies, gender, birthdate, twofa, status)
                driver.quit()
            elif self.account_fullverify:
                print("Account fully verified. Proceeding to click the OK button.")
                btn_ok = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "/html/body/div[1]/div/div[2]/div/div[1]/div/div/div[3]/div[2]/form/div/button"))
                )
                btn_ok.click()
                time.sleep(2)

                btnSendcode = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "/html/body/div[1]/div[1]/div[3]/div/div[1]/div/div/form/div[3]/button"))
                )
                btnSendcode.click()
                time.sleep(2)

                # Proceed with email verification
                try:
                    if self.handle_email_verification(driver, email, passmail, self.stop_flag):
                        status = "Fully Verified"
                        print("Account fully verified.")
                                    # Emit Progress Signal
                        twofa = None
                        self.progress.emit(full_name, uid, password, phone_number, email, cookies, gender, birthdate, twofa, status)
                    else:
                        status = "Successful"
                        print("Email verification failed.")
                                    # Emit Progress Signal
                        twofa = None
                        self.progress.emit(full_name, uid, password, phone_number, email, cookies, gender, birthdate, twofa, status)
                    
                except Exception as e:
                    print(f"Error during email verification: {e}")
                    status = "Successful"
            else:
                print("No conditions met. Quitting the driver.")
                driver.quit()



        except Exception as e:
            print(f"Error during account registration: {e}")
            status = "Fail"
        finally:
            driver.quit()

    def handle_email_verification(self, driver, email, passmail, stop_flag):
        """
        Handles the email verification process, including switching to email,
        entering the email address, fetching the verification code, and confirming it.
        Returns True if verification is successful, False otherwise.
        """
        try:
            if stop_flag.is_set():
                logging.info("Stop flag detected. Exiting handle_email_verification.")
                return False

            # Attempt to locate the "Switch to Email" button
            btnidntgetcode = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "/html/body/div[1]/div/div[3]/div/div[1]/div[1]/div/div/div/a"))
            )
            print("Detected phone validation failure. Switching to email.")
            btnidntgetcode.click()

            if stop_flag.is_set():
                logging.info("Stop flag detected. Exiting handle_email_verification.")
                return False

            # Click the "Confirm with Email" button
            btncfwithmail = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "/html/body/div[1]/div/div[3]/div/div[1]/div[1]/div/div/div/a[1]"))
            )
            btncfwithmail.click()

            if stop_flag.is_set():
                logging.info("Stop flag detected. Exiting handle_email_verification.")
                return False

            # Enter the assigned email
            email_field = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.XPATH, "/html/body/div[1]/div[1]/div[3]/div/div[1]/div/div/div/form/div[1]/div/input"))
            )
            email_field.send_keys(email)

            if stop_flag.is_set():
                logging.info("Stop flag detected. Exiting handle_email_verification.")
                return False

            # Proceed to the next step
            btnadd = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "/html/body/div[1]/div[1]/div[3]/div/div[1]/div/div/div/form/div[2]/div[1]/button"))
            )
            btnadd.click()
            
            if stop_flag.is_set():
                logging.info("Stop flag detected. Exiting handle_email_verification.")
                return False
            time.sleep(15)
            for _ in range(30):
                if stop_flag.is_set():
                    logging.info("Stop flag detected. Exiting handle_email_verification.")
                    return False
                verification_code = self.get_verification_code(email, passmail)
                if verification_code:
                    print(f"Verification code found: {verification_code}")
                    # Enter the verification code
                    code_input_field = WebDriverWait(driver, 10).until(
                        EC.visibility_of_element_located((By.XPATH, "/html/body/div[1]/div[1]/div[3]/div/div/div[1]/div/div/div/form/div/input"))
                    )
                    code_input_field.send_keys(verification_code)
                    if stop_flag.is_set():
                        logging.info("Stop flag detected. Exiting handle_email_verification.")
                        return False
                    # Confirm the verification code
                    btncfcode = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, "/html/body/div[1]/div[1]/div[3]/div/div/div[1]/div/div/div/form/a"))
                    )
                    btncfcode.click()
                    time.sleep(15)  # Wait for confirmation
                    return True  # Indicate success
                else:
                    print("Verification code not found. Retrying in 5 seconds...")
                    time.sleep(5)  # Wait before retrying
            # If no verification code is found after retries
            print("Verification code not found after 5 attempts.")
            return False
        except TimeoutException as e:
            print(f"Timeout occurred during email verification: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error during email verification: {e}")
            return False
        
def resource_path(relative_path):
    """Get the absolute path to a resource, works for dev and PyInstaller."""
    if hasattr(sys, '_MEIPASS'):  # Check if running as a PyInstaller bundle
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

class Ui_Dialog(object):
    def setupUi(self, Dialog):
        # Initialize status counters
        self.total_count = 0
        self.successful_count = 0
        self.fully_verified_count = 0
        self.checkpoint_count = 0
        self.fail_count = 0
        self.verticalLayout = QtWidgets.QVBoxLayout()
        self.accountManagerLayout = QtWidgets.QVBoxLayout()
        self.stop_flags = []
        self.mailList = []
        self.output_lock = threading.Lock()
        self.Dialog = Dialog
        Dialog.setObjectName("Dialog")
        Dialog.setWindowTitle("SocialForge Dev by Chen Lisal")
        
        # Set the window flags to include minimize and maximize buttons
        Dialog.setWindowFlags(Dialog.windowFlags() | 
                              QtCore.Qt.WindowMinimizeButtonHint | 
                              QtCore.Qt.WindowMaximizeButtonHint)
        
        # Dynamically determine the icon path
        icon_path = resource_path("img/letter-s.ico")

        # Set the application icon
        APP_ID = "com.khmer.SocialForge"
            # Required for taskbar icon visibility on Windows
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        
        if os.path.exists(icon_path):
            Dialog.setWindowIcon(QtGui.QIcon(icon_path))
        else:
            print(f"Icon file not found: {icon_path}")
        
        Dialog.resize(800, 600)


        # Set professional background, text color, and font
        Dialog.setStyleSheet("""
            QDialog {
                background-color: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 #1E1E2F, stop: 1 #2C2C3E);
                color: white; /* Light text color */
                font-family: 'Segoe UI', sans-serif; /* Professional font */
                font-size: 14px; /* Default font size */
            }
            QLabel {
                color: white; /* Light gray text */
                font-size: 14px;
            }
            QGroupBox {
                border: 1px solid #444;
                border-radius: 5px;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 3px;
                color: white;
                font-weight: bold; /* Bold titles for groups */
            }
            QPushButton {
                background-color: #333;
                color: white;
                border: 1px solid #444;
                border-radius: 5px;
                padding: 10px;
                font-family: 'Segoe UI', sans-serif; /* Professional font */
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #222; /* Darker green on hover */
            }
            QPushButton#stopButton {
                background-color: #333; /* Red button for Stop */
            }
            QPushButton#stopButton:hover {
                background-color: #222; /* Darker red on hover */
            }
            QTableWidget {
                background-color: #FFFFFF; /* Dark table background */
                color: black; /* White table text */
                border: 1px solid #444;
                gridline-color: #555; /* Gridline color */
                selection-background-color: ; /* Selection highlight */
                font-family: 'Segoe UI', sans-serif; /* Professional font */
                font-size: 13px; /* Slightly smaller font for tables */
            }
            QHeaderView::section {
                background-color: #2C2C3E; /* Header background */
                color: white; /* Header text */
                padding: 4px;
                border: 1px solid #444;
                font-family: 'Segoe UI', sans-serif; /* Professional font */
                font-size: 10px;
                font-weight: bold; /* Bold headers */
            }
            QRadioButton, QCheckBox {
                color: white; /* White text for radio buttons and checkboxes */
                font-family: 'Segoe UI', sans-serif; /* Professional font */
                font-size: 14px;
            }
            QTabWidget::pane {
                border: 1px solid #444;
                background-color: #2C2C3E;
            }
            QTabBar::tab {
                background-color: #1E1E2F;
                color: white;
                padding: 10px;
                border: 1px solid #444;
            }
            QTabBar::tab:selected {
                background-color: #858585; /* Highlight selected tab */
                color: white;
            }
        """)

        # Main layout
        self.verticalLayout = QtWidgets.QVBoxLayout(Dialog)

        # Add a Tab Widget for Navigation Bar
        self.tabWidget = QtWidgets.QTabWidget()
        self.tabWidget.setObjectName("tabWidget")

        # Tab 1: Account Manager
        self.accountManagerTab = QtWidgets.QWidget()
        self.accountManagerLayout = QtWidgets.QVBoxLayout(self.accountManagerTab)

        # Horizontal Layout for Threads and Account Options Groups
        horizontal_group_layout = QtWidgets.QHBoxLayout()

        # Threads and Delay Group
        self.groupThreads = QtWidgets.QGroupBox("Process Configuration")
        self.groupThreads.setStyleSheet("""
            QGroupBox {
                border: 1px solid #444;
                border-radius: 5px;
                margin-top: 3px; /* Reduce space above the group box */
                padding: 4px; /* Tight padding around the content */
                background-color: #2C2C3E; /* Dark background for contrast */
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center; /* Center the title */
                padding: 0 8px; /* Adjust horizontal padding for better fit */
                color: white;
                font-weight: bold;
                font-size: 12px; /* Slightly smaller font size for compactness */
                background-color: #2C2C3E; /* Match background color to avoid gaps */
            }
        """)
        self.layoutThreads = QtWidgets.QGridLayout()  # Use GridLayout for better alignment

        # Threads Input
        threads_label = QtWidgets.QLabel("Threads:")
        threads_label.setStyleSheet("color: white; font-size: 12px;")
        self.threadsInput = QtWidgets.QSpinBox()
        self.threadsInput.setFixedWidth(60)  # Short length for better alignment
        self.threadsInput.setStyleSheet("""
            QSpinBox {
                background-color: #333;
                color: white;
                border: 1px solid #444;
                border-radius: 5px;
                padding: 5px;
            }
        """)
        self.layoutThreads.addWidget(threads_label, 0, 0)  # Row 0, Column 0
        self.layoutThreads.addWidget(self.threadsInput, 0, 1)  # Row 0, Column 1

        # Delay Input
        delay_label = QtWidgets.QLabel("Delay:")
        delay_label.setStyleSheet("color: white; font-size: 12px;")
        self.delayInput = QtWidgets.QSpinBox()
        self.delayInput.setFixedWidth(60)  # Short length for better alignment
        self.delayInput.setStyleSheet("""
            QSpinBox {
                background-color: #333;
                color: white;
                border: 1px solid #444;
                border-radius: 5px;
                padding: 5px;
            }
        """)
        self.layoutThreads.addWidget(delay_label, 0, 2)  # Row 0, Column 2
        self.layoutThreads.addWidget(self.delayInput, 0, 3)  # Row 0, Column 3

        # Stop After Input
        stop_label = QtWidgets.QLabel("Stop After:")
        stop_label.setStyleSheet("color: white; font-size: 12px;")
        self.stopInput = QtWidgets.QSpinBox()
        self.stopInput.setFixedWidth(60)  # Short length for better alignment
        self.stopInput.setStyleSheet("""
            QSpinBox {
                background-color: #333;
                color: white;
                border: 1px solid #444;
                border-radius: 5px;
                padding: 5px;
            }
        """)
        self.layoutThreads.addWidget(stop_label, 0, 4)  # Row 0, Column 4
        self.layoutThreads.addWidget(self.stopInput, 0, 5)  # Row 0, Column 5

        # Add stretch to ensure proper alignment
        self.layoutThreads.setColumnStretch(6, 1)  # Add stretch after the last column

        # Set Layout for Threads and Delay Group
        self.groupThreads.setLayout(self.layoutThreads)

        # Add Threads and Delay Group to the horizontal layout
        horizontal_group_layout.addWidget(self.groupThreads)

        # Account Options Group
        self.groupOptions = QtWidgets.QGroupBox("Account Options")
        self.groupOptions.setStyleSheet("""
            QGroupBox {
                border: 1px solid #444;
                border-radius: 5px;
                margin-top: 3px; /* Reduce space above the group box */
                padding: 4px; /* Tight padding around the content */
                background-color: #2C2C3E; /* Dark background for contrast */
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center; /* Center the title */
                padding: 0 8px; /* Adjust horizontal padding for better fit */
                color: white;
                font-weight: bold;
                font-size: 12px; /* Slightly smaller font size for compactness */
                background-color: #2C2C3E; /* Match background color to avoid gaps */
            }
        """)
        self.layoutOptions = QtWidgets.QVBoxLayout()

        # Gender ComboBox
        gender_layout = QtWidgets.QHBoxLayout()
        gender_label = QtWidgets.QLabel("Gender:")
        gender_label.setStyleSheet("color: white; font-size: 12px;")
        self.genderCombo = QtWidgets.QComboBox()
        self.genderCombo.addItems(["Male", "Female", "Random"])
        self.genderCombo.setFixedWidth(100)  # Shorter width for compactness
        self.genderCombo.setStyleSheet("""
            QComboBox {
                background-color: #333;
                color: white;
                border: 1px solid #444;
                border-radius: 5px;
                padding: 5px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
            }
        """)
        gender_layout.addWidget(gender_label)
        gender_layout.addWidget(self.genderCombo)
        gender_layout.addStretch()  # Align widgets to the left
        self.layoutOptions.addLayout(gender_layout)

        # Combined Row for Phone Checkbox and Password Radio Buttons
        combined_row_layout = QtWidgets.QHBoxLayout()

        # Generate Random Phone Number Checkbox
        self.randomPhoneCheckbox = QtWidgets.QCheckBox("Random Phone Number")
        self.randomPhoneCheckbox.setStyleSheet("color: white; font-size: 12px;")
        combined_row_layout.addWidget(self.randomPhoneCheckbox)

        # Password Options Group (Radio Buttons)
        password_radio_layout = QtWidgets.QHBoxLayout()
        password_radio_layout.setSpacing(10)

        self.radio_random_password = QtWidgets.QRadioButton("Random Password")
        self.radio_custom_password = QtWidgets.QRadioButton("Custom Password")

        # Apply consistent styling
        for radio_button in (self.radio_random_password, self.radio_custom_password):
            radio_button.setStyleSheet("color: white; font-size: 12px;")

        # Add radio buttons to a QButtonGroup
        self.password_group = QtWidgets.QButtonGroup(self.groupOptions)
        self.password_group.addButton(self.radio_random_password)
        self.password_group.addButton(self.radio_custom_password)

        # Set default selection
        self.radio_random_password.setChecked(True)

        # Add radio buttons to the layout
        password_radio_layout.addWidget(self.radio_random_password)
        password_radio_layout.addWidget(self.radio_custom_password)

        # Custom Password Field (Enabled only when "Custom Password" is selected)
        self.customPasswordLineEdit = QtWidgets.QLineEdit()
        self.customPasswordLineEdit.setEnabled(False)  # Disabled by default
        self.customPasswordLineEdit.setFixedWidth(120)  # Shorter width for compactness
        self.customPasswordLineEdit.setStyleSheet("""
            QLineEdit {
                background-color: #333;
                color: white;
                border: 1px solid #444;
                border-radius: 5px;
                padding: 5px;
            }
        """)

        # Toggle Password Field Visibility
        self.radio_custom_password.toggled.connect(self.togglePasswordField)

        # Add the custom password field to the layout
        password_radio_layout.addWidget(self.customPasswordLineEdit)

        # Add stretch to ensure proper alignment
        password_radio_layout.addStretch()

        # Add the password radio button layout to the combined row layout
        combined_row_layout.addLayout(password_radio_layout)
        self.layoutOptions.addLayout(combined_row_layout)

        # Verification Radio Buttons in the Same Row
        verification_layout = QtWidgets.QHBoxLayout()
        verification_layout.setSpacing(10)

        self.radio_no_verify = QtWidgets.QRadioButton("No Verify")
        self.radio_full_verify = QtWidgets.QRadioButton("Full Verify")

        # Apply consistent styling
        for radio_button in (self.radio_no_verify, self.radio_full_verify):
            radio_button.setStyleSheet("color: white; font-size: 12px;")

        # Add radio buttons to a QButtonGroup
        self.verification_group = QtWidgets.QButtonGroup(self.groupOptions)
        self.verification_group.addButton(self.radio_no_verify)
        self.verification_group.addButton(self.radio_full_verify)

        # Set default selection
        self.radio_no_verify.setChecked(True)

        # Add radio buttons to the layout
        verification_layout.addWidget(self.radio_no_verify)
        verification_layout.addWidget(self.radio_full_verify)

        # Add stretch to ensure proper alignment
        verification_layout.addStretch()

        # Add the verification layout to the main layout
        self.layoutOptions.addLayout(verification_layout)

        # Random Name Generation Radio Buttons (Compact Layout)
        name_generation_layout = QtWidgets.QGridLayout()
        name_generation_layout.setSpacing(10)  # Add spacing between elements

        # Add a label for the "Name Option" section
        name_option_label = QtWidgets.QLabel("Name Options")
        name_option_label.setStyleSheet("color: white; font-size: 12px; font-family: 'Segoe UI', sans-serif; font-weight: bold;")  # Make the label bold for emphasis
        name_generation_layout.addWidget(name_option_label, 0, 0, 1, 3)  # Span across all columns (Row 0)

        # Row 1: Random Name, English Name, Thai Name
        self.radio_random_name = QtWidgets.QRadioButton("Random")
        self.radio_english_name = QtWidgets.QRadioButton("English")
        self.radio_thai_name = QtWidgets.QRadioButton("Thai")
        name_generation_layout.addWidget(self.radio_random_name, 1, 0)  # Row 1, Column 0
        name_generation_layout.addWidget(self.radio_english_name, 1, 1)  # Row 1, Column 1
        name_generation_layout.addWidget(self.radio_thai_name, 1, 2)     # Row 1, Column 2

        # Row 2: Khmer Name, Chinese Name, Default from Text File
        self.radio_khmer_name = QtWidgets.QRadioButton("Khmer")
        self.radio_chinese_name = QtWidgets.QRadioButton("Chinese")
        self.radio_file_name = QtWidgets.QRadioButton("From File")
        name_generation_layout.addWidget(self.radio_khmer_name, 2, 0)    # Row 2, Column 0
        name_generation_layout.addWidget(self.radio_chinese_name, 2, 1)  # Row 2, Column 1
        name_generation_layout.addWidget(self.radio_file_name, 2, 2)     # Row 2, Column 2

        # Group the radio buttons
        self.name_source_group = QtWidgets.QButtonGroup(self.groupOptions)
        self.name_source_group.addButton(self.radio_random_name)
        self.name_source_group.addButton(self.radio_english_name)
        self.name_source_group.addButton(self.radio_thai_name)
        self.name_source_group.addButton(self.radio_khmer_name)
        self.name_source_group.addButton(self.radio_chinese_name)
        self.name_source_group.addButton(self.radio_file_name)

        # Set default selection
        self.radio_random_name.setChecked(True)

        # Add the grid layout to the main options layout
        self.layoutOptions.addLayout(name_generation_layout)
        # Set Layout for Account Options Group
        self.groupOptions.setLayout(self.layoutOptions)

        # Add Account Options Group to the horizontal layout
        horizontal_group_layout.addWidget(self.groupOptions)

        # Add the horizontal layout to the main layout
        self.accountManagerLayout.addLayout(horizontal_group_layout)

        # Action Buttons and Output Directory Layout
        action_and_directory_layout = QtWidgets.QHBoxLayout()

        # Start Button
        self.startButton = QtWidgets.QPushButton("Start")
        self.startButton.setObjectName("startButton")  # For styling
        self.startButton.setIcon(QtGui.QIcon('./Resources/img/start.png'))
        action_and_directory_layout.addWidget(self.startButton)

        # Stop Button
        self.stopButton = QtWidgets.QPushButton("Stop")
        self.stopButton.setObjectName("stopButton")  # For styling
        self.stopButton.setIcon(QtGui.QIcon('./Resources/img/stop.png'))
        action_and_directory_layout.addWidget(self.stopButton)

        # Open Output Folder Button
        self.openOutputFolderButton = QtWidgets.QPushButton("Output")
        self.openOutputFolderButton.setIcon(QtGui.QIcon('./Resources/img/flames.png'))
        self.openOutputFolderButton.clicked.connect(self.open_output_folder)
        action_and_directory_layout.addWidget(self.openOutputFolderButton)



        # Label for the output directory
        output_directory_label = QtWidgets.QLabel("Output Directory:")
        output_directory_label.setStyleSheet("color: white; font-size: 12px;")
        action_and_directory_layout.addWidget(output_directory_label)

        # Input field for the output directory
        self.outputDirectoryInput = QtWidgets.QLineEdit()
        self.outputDirectoryInput.setPlaceholderText("Select or enter output directory")
        self.outputDirectoryInput.setStyleSheet("""
            QLineEdit {
                background-color: #333;
                color: white;
                border: 1px solid #444;
                border-radius: 5px;
                padding: 5px;
            }
        """)
        self.outputDirectoryInput.setFixedWidth(300)  # Set a fixed width for the input field
        action_and_directory_layout.addWidget(self.outputDirectoryInput)

        # Browse Button
        self.browseButton = QtWidgets.QPushButton("Browse")
        self.browseButton.setIcon(QtGui.QIcon('./Resources/img/browse.png'))
        self.browseButton.clicked.connect(self.select_output_directory)
        self.browseButton.setStyleSheet("""
            QPushButton {
                background-color: #0088cc;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 5px 10px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #005f99;
            }
        """)
        action_and_directory_layout.addWidget(self.browseButton)
        # Spacer to separate buttons from the output directory section
        spacer = QtWidgets.QSpacerItem(20, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        action_and_directory_layout.addItem(spacer)
        # Add the combined layout to the main layout
        self.accountManagerLayout.addLayout(action_and_directory_layout)

        # Display Table
        self.tableWidget = QtWidgets.QTableWidget()
        self.tableWidget.setColumnCount(12)
        self.tableWidget.setHorizontalHeaderLabels(
            ["Select", "No.", "Name", "UID", "Password", "Phone", "Email", "Cookies", "Gender", "Birthdate","2Fa", "Status"]
        )
        # Set the table to expand and fill available space
        
        #self.tableWidget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.tableWidget.setContextMenuPolicy(Qt.CustomContextMenu)  # Enable custom context menu
        self.tableWidget.customContextMenuRequested.connect(lambda pos: self.show_context_menu(pos, self.tableWidget))

        #self.tableWidget.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.tableWidget.verticalHeader().setVisible(False)  # Hide row numbers
        
        #self.tableWidget.setShowGrid(False)  # Hide grid lines
        # Make columns stretch to fit the available width
        #header = self.tableWidget.horizontalHeader()
        #header.setSectionResizeMode(QtWidgets.QHeaderView.Stretch)  # Stretch all columns

        # Add the table widget to the layout
        self.accountManagerLayout.addWidget(self.tableWidget)

        # Optional: Add stretch to push other widgets above the table
        #self.accountManagerLayout.addStretch()
        # Action Buttons and Status Counters Layout
        action_layout = QtWidgets.QHBoxLayout()

        # Status Counters Display
        self.statusLayout = QtWidgets.QHBoxLayout()
        self.statusLabel = QtWidgets.QLabel("")
        self.statusLabel.setStyleSheet("font-weight: bold; font-size: 1px;")
        self.statusCountsLabel = QtWidgets.QLabel("")
        self.updateStatusCounts()  # Initialize status counts
        self.statusLayout.addWidget(self.statusLabel)
        self.statusLayout.addWidget(self.statusCountsLabel)

        # Add the status layout to the action layout
        action_layout.addLayout(self.statusLayout)  # Use addLayout, not addWidget

        # Add spacer to push elements to the left
        spacer = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        action_layout.addItem(spacer)

        # Add the action layout to the main layout
        self.accountManagerLayout.addLayout(action_layout)
        

        # Add Account Manager Tab to Tab Widget
        tab_index = self.tabWidget.addTab(self.accountManagerTab, "Config && Accounts")
        self.tabWidget.setTabIcon(tab_index, QtGui.QIcon('./Resources/img/settings.png')) 

        # Tab 2: Settings
        self.settingsTab = QtWidgets.QWidget()
        self.settingsLayout = QtWidgets.QVBoxLayout(self.settingsTab)

        # Title Label for Settings Page
        self.settingsLabel = QtWidgets.QLabel("Generator data")
        self.settingsLabel.setStyleSheet("""
            font-size: 24px;
            font-weight: bold;
            color: white;
            margin-bottom: 15px;
        """)
        self.settingsLayout.addWidget(self.settingsLabel, alignment=QtCore.Qt.AlignCenter)

        # Input for Email Format
        email_format_layout = QtWidgets.QHBoxLayout()
        self.emailFormatLabel = QtWidgets.QLabel("Email Format (e.g., prefix+{}@yandex.com):")
        self.emailFormatLabel.setStyleSheet("color: white; font-size: 14px;")
        self.emailFormatInput = QtWidgets.QLineEdit()
        self.emailFormatInput.setPlaceholderText("prefix+{}@yandex.com")
        self.emailFormatInput.setStyleSheet("""
            QLineEdit {
                background-color: #333;
                color: white;
                border: 1px solid #444;
                border-radius: 5px;
                padding: 5px;
            }
        """)
        email_format_layout.addWidget(self.emailFormatLabel)
        email_format_layout.addWidget(self.emailFormatInput)
        self.settingsLayout.addLayout(email_format_layout)

        # Input for Password
        password_layout = QtWidgets.QHBoxLayout()
        self.passwordLabel = QtWidgets.QLabel("Password:")
        self.passwordLabel.setStyleSheet("color: white; font-size: 14px;")
        self.passwordInput = QtWidgets.QLineEdit()
        self.passwordInput.setPlaceholderText("Enter password here")
        self.passwordInput.setEchoMode(QtWidgets.QLineEdit.Password)  # Mask password input
        self.passwordInput.setStyleSheet("""
            QLineEdit {
                background-color: #333;
                color: white;
                border: 1px solid #444;
                border-radius: 5px;
                padding: 5px;
            }
        """)
        password_layout.addWidget(self.passwordLabel)
        password_layout.addWidget(self.passwordInput)
        self.settingsLayout.addLayout(password_layout)

        # Buttons Layout
        buttons_layout = QtWidgets.QHBoxLayout()

        # Button to Generate Random Names
        self.generateNamesButton = QtWidgets.QPushButton("Generate Random Names")
        self.generateNamesButton.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45A049;
            }
        """)
        self.generateNamesButton.clicked.connect(self.generate_random_names)
        buttons_layout.addWidget(self.generateNamesButton)

        # Button to Generate Emails and Passwords
        self.generateEmailsButton = QtWidgets.QPushButton("Generate Emails and Passwords")
        self.generateEmailsButton.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1E88E5;
            }
        """)
        self.generateEmailsButton.clicked.connect(self.generate_emails_and_passwords)
        buttons_layout.addWidget(self.generateEmailsButton)

        # Add buttons layout to the main settings layout
        self.settingsLayout.addLayout(buttons_layout)

        # Add spacer to push content upwards
        spacer = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.settingsLayout.addItem(spacer)

        # Add Settings Tab to Tab Widget
        tab_index = self.tabWidget.addTab(self.settingsTab, "Generate data")
        self.tabWidget.setTabIcon(tab_index, QtGui.QIcon('./Resources/img/folder-management.png')) 


        # Add Tab Widget to Main Layout
        self.verticalLayout.addWidget(self.tabWidget)

                # Add a new tab for "Contact Admin"
        self.contactAdminTab = QWidget()
        self.contactAdminTab = QWidget()
        tab_index = self.tabWidget.addTab(self.contactAdminTab, "Contact Admin")
        self.tabWidget.setTabIcon(tab_index, QtGui.QIcon('./Resources/img/admin.png')) 

        # Layout for the "Contact Admin" tab
        contact_admin_layout = QVBoxLayout(self.contactAdminTab)

        # Load saved data
        
        #expiry_date = saved_data.get("expiry_date")

        # Add a label to display the QR code image
        qr_label = QLabel("Scan the QR Code to Renew License by")
        qr_label.setStyleSheet("color: white; font-size: 12px; font-family: 'Segoe UI', sans-serif; font-weight: bold;")
        contact_admin_layout.addWidget(qr_label)

        # Load and display the QR code image
        qr_image_path = self.get_icon_path("qr.jpg")  # Get the absolute path to the QR image
        qr_pixmap = QPixmap(qr_image_path)
        qr_image_label = QLabel()
        qr_image_label.setPixmap(qr_pixmap.scaled(400, 400, aspectRatioMode=True))  # Resize the image if needed
        contact_admin_layout.addWidget(qr_image_label)

        # Add a spacer to separate the QR code and the button
        contact_admin_layout.addSpacing(20)

        # Add a button to open the Telegram link
        telegram_button = QPushButton("Contact Admin")

        telegram_button.setStyleSheet("""
            QPushButton {
                background-color: #0088cc;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #005f99;
            }
        """)
        telegram_button.clicked.connect(lambda: webbrowser.open("https://t.me/chen_lisal"))  # Replace with your Telegram link
        contact_admin_layout.addWidget(telegram_button)

        # Align everything to the center
        contact_admin_layout.setAlignment(Qt.AlignCenter)

        # Add the "Data Management" tab
        self.dataManagementTab = QtWidgets.QWidget()
        self.setupDataManagementTab(self.dataManagementTab)

        # Add the tab to the QTabWidget and get its index
        tab_index = self.tabWidget.addTab(self.dataManagementTab, "Data Management")

        # Set the icon for the "Data Management" tab
        self.tabWidget.setTabIcon(tab_index, QtGui.QIcon('./Resources/img/file.png'))



        # Connect Signals
        self.startButton.clicked.connect(self.startProcess)
        self.stopButton.clicked.connect(self.stopProcess)
    
    
    def setupDataManagementTab(self, tab):
        # Layout for the Data Management tab
        layout = QtWidgets.QVBoxLayout(tab)

        # Horizontal layout for Import button, Status Filter, Search Box, and Find Button
        top_layout = QtWidgets.QHBoxLayout()

        # Import Button
        self.importButton = QtWidgets.QPushButton("Import Data")
        self.importButton.setIcon(QtGui.QIcon('./Resources/img/txt.png'))
        self.importButton.clicked.connect(self.import_data)
        top_layout.addWidget(self.importButton)

        self.save_all_button = QtWidgets.QPushButton("Save to CSV")
        self.save_all_button.setIcon(QtGui.QIcon('./Resources/img/csv-file.png'))
        self.save_all_button.clicked.connect(self.save_all_data_to_csv)
        top_layout.addWidget(self.save_all_button)
        # Delete Rows by UID Button
        self.deleteByUIDButton = QtWidgets.QPushButton("Delete Rows by UID")
        self.deleteByUIDButton.setIcon(QtGui.QIcon('./Resources/img/recycle-bin.png'))
        self.deleteByUIDButton.clicked.connect(self.delete_rows_by_uid)
        top_layout.addWidget(self.deleteByUIDButton)

        # UID Input Field
        self.uidInput = QtWidgets.QLineEdit()
        self.uidInput.setPlaceholderText("Enter UIDs to delete (space-separated)")
        top_layout.addWidget(self.uidInput)

        # Status Filter Menu
        self.statusFilterLabel = QtWidgets.QLabel("Filter by Status:")
        self.statusFilterLabel.setStyleSheet("color: white; font-size: 12px; font-family: 'Segoe UI', sans-serif; font-weight: bold;")
        top_layout.addWidget(self.statusFilterLabel)
        self.statusFilterMenu = QtWidgets.QComboBox()
        self.statusFilterMenu.addItems(["All", "Successful", "Fully Verified", "Checkpoint", "Fail","Live","Die"])
        self.statusFilterMenu.currentTextChanged.connect(self.filter_table_by_status)
        top_layout.addWidget(self.statusFilterMenu)

        # Search Box
        self.searchBox = QtWidgets.QLineEdit()
        self.searchBox.setPlaceholderText("Enter search text...")
        top_layout.addWidget(self.searchBox)

        # Find Button
        self.findButton = QtWidgets.QPushButton("Find")
        self.findButton.setIcon(QtGui.QIcon('./Resources/img/search.png'))
        self.findButton.clicked.connect(self.search_table)
        top_layout.addWidget(self.findButton)

        # Add the top layout to the main layout
        layout.addLayout(top_layout)

        # Table Widget
        self.dataTable = QtWidgets.QTableWidget()
        self.dataTable.setColumnCount(13)
        self.dataTable.setHorizontalHeaderLabels(
            ["Select", "No.", "Name", "UID", "Password", "Phone", "Email", "Cookies", "Gender", "Birthdate", "2FA", "Status","Created On"]
        )
        self.dataTable.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)  # Enable custom context menu
        self.dataTable.verticalHeader().setVisible(False)
        self.dataTable.customContextMenuRequested.connect(lambda pos: self.show_context_menu(pos, self.dataTable))
        layout.addWidget(self.dataTable)

        # Initialize unique UIDs set
        self.unique_uids = set()

    def save_all_data_to_csv(self):
        try:
            # Open a file dialog to select the output file
            options = QtWidgets.QFileDialog.Options()
            file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self.Dialog,  # Use self.Dialog as the parent (a QWidget)
                "Save CSV File", 
                "", 
                "CSV Files (*.csv);;All Files (*)", 
                options=options
            )
            if not file_path:
                return  # User canceled the dialog

            # Prepare data for export
            rows = []
            header = [
                "No.", "Name", "UID", "Password", "Phone", "Email",
                "Cookies", "Gender", "Birthdate", "2FA", "Status", "Created On"
            ]
            rows.append(header)  # Add header row

            # Extract data from the table
            for row in range(self.dataTable.rowCount()):
                row_data = []
                for col in range(1, self.dataTable.columnCount()):  # Skip the "Select" column
                    item = self.dataTable.item(row, col)
                    row_data.append(item.text() if item else "")
                rows.append(row_data)

            if len(rows) == 1:  # Only the header row exists
                QtWidgets.QMessageBox.warning(
                    self.Dialog,  # Use self.Dialog as the parent
                    "No Data", 
                    "The table is empty. Nothing to save."
                )
                return

            # Write data to CSV file
            with open(file_path, mode="w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerows(rows)

            QtWidgets.QMessageBox.information(
                self.Dialog,  # Use self.Dialog as the parent
                "Success", 
                f"All data saved successfully to {file_path}"
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self.Dialog,  # Use self.Dialog as the parent
                "Error", 
                f"Failed to save data: {str(e)}"
            )
            
    def apply_conditional_formatting(self, table, row_position, status):
        """
        Applies conditional formatting to a row based on its status.
        """
        # Define colors for each status
        if status == "Live":
            row_color = "#d4edb6"  # Light green
        elif status == "Die":
            row_color = "#FFCDD2"  # Light red
        elif status == "Successful":
            row_color = "#FFFFFF"  # Green
        elif status == "Fully Verified":
            row_color = "#FFFFFF"  # Blue
        elif status == "Checkpoint":
            row_color = "#FFC107"  # Yellow
        elif status == "Fail":
            row_color = "#ffadad"  # Red
        else:
            row_color = "#FFFFFF"  # White (default)

        # Apply the background color to the entire row
        for col in range(table.columnCount()):
            item = table.item(row_position, col)
            if item:
                item.setBackground(QtGui.QColor(row_color))

    def import_data(self):
        """Imports data from a file into the table."""
        options = QtWidgets.QFileDialog.Options()
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self.Dialog, "Import Data File", "", "Text Files (*.txt);;All Files (*)", options=options)
        if not file_path:
            return

        try:
            # Clear the table before importing new data
            self.dataTable.setRowCount(0)
            self.unique_uids.clear()

            with open(file_path, "r", encoding="utf-8") as file:
                lines = file.readlines()

            for line in lines:
                fields = line.strip().split("|")
                if len(fields) != 11:
                    print(f"Skipping invalid line: {line}")
                    continue

                name, uid, password, phone, email, cookies, gender, birthdate, twofa, status, timestamp = fields

                # Check for duplicate UID
                if uid in self.unique_uids:
                    print(f"Duplicate UID found: {uid}. Skipping.")
                    continue

                # Add the UID to the set
                self.unique_uids.add(uid)

                # Insert the data into the table
                row_position = self.dataTable.rowCount()
                self.dataTable.insertRow(row_position)

                # Add checkbox in the first column
                checkbox_item = QtWidgets.QTableWidgetItem()
                checkbox_item.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
                checkbox_item.setCheckState(QtCore.Qt.Unchecked)
                self.dataTable.setItem(row_position, 0, checkbox_item)

                # Add the remaining data
                self.dataTable.setItem(row_position, 1, QtWidgets.QTableWidgetItem(str(row_position + 1)))  # Row number
                self.dataTable.setItem(row_position, 2, QtWidgets.QTableWidgetItem(name))
                self.dataTable.setItem(row_position, 3, QtWidgets.QTableWidgetItem(uid))
                self.dataTable.setItem(row_position, 4, QtWidgets.QTableWidgetItem(password))
                self.dataTable.setItem(row_position, 5, QtWidgets.QTableWidgetItem(phone))
                self.dataTable.setItem(row_position, 6, QtWidgets.QTableWidgetItem(email))
                self.dataTable.setItem(row_position, 7, QtWidgets.QTableWidgetItem(cookies))
                self.dataTable.setItem(row_position, 8, QtWidgets.QTableWidgetItem(gender))
                self.dataTable.setItem(row_position, 9, QtWidgets.QTableWidgetItem(birthdate))
                self.dataTable.setItem(row_position, 10, QtWidgets.QTableWidgetItem(twofa))
                self.dataTable.setItem(row_position, 11, QtWidgets.QTableWidgetItem(status))
                self.dataTable.setItem(row_position, 12, QtWidgets.QTableWidgetItem(timestamp))

                # Apply conditional formatting based on status
                self.apply_conditional_formatting(self.dataTable, row_position, status)

            # Update row numbers after importing all rows
            self.update_row_numbers(self.dataTable)

            QtWidgets.QMessageBox.information(self.Dialog, "Success", f"Loaded {len(lines)} lines from {file_path}.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self.Dialog, "Error", f"Failed to import data: {str(e)}")

    def delete_rows_by_uid(self):
        """
        Deletes all rows from the table that match any of the UIDs entered in the input box.
        """
        uids_to_delete = self.uidInput.text().strip().split()  # Split input by whitespace or newlines
        if not uids_to_delete:
            QtWidgets.QMessageBox.warning(self.Dialog, "Input Error", "Please enter UIDs to delete.")
            return

        rows_to_delete = []
        deleted_uids = set()

        # Find all rows matching any of the UIDs
        for row in range(self.dataTable.rowCount()):
            uid_item = self.dataTable.item(row, 3)  # UID is in the fourth column (index 3)
            if uid_item and uid_item.text() in uids_to_delete:
                rows_to_delete.append(row)
                deleted_uids.add(uid_item.text())

        if not rows_to_delete:
            QtWidgets.QMessageBox.information(self.Dialog, "No Matches", f"No rows found with the provided UIDs.")
            return

        # Remove rows in reverse order to avoid index shifting issues
        for row in reversed(rows_to_delete):
            self.dataTable.removeRow(row)

        # Remove the UIDs from the unique_uids set
        self.unique_uids -= deleted_uids
        self.update_row_numbers(self.dataTable)

        QtWidgets.QMessageBox.information(self.Dialog, "Success", f"Deleted {len(rows_to_delete)} rows with UIDs:\n{', '.join(deleted_uids)}")

    def delete_checked_rows(self, table):
        """
        Deletes rows where the checkbox in the "Select" column is checked.
        """
        rows_to_delete = []
        
        # Identify rows to delete
        for row in range(self.dataTable.rowCount()):
            checkbox_item = self.dataTable.item(row, 0)  # "Select" column
            if checkbox_item and checkbox_item.checkState() == QtCore.Qt.Checked:
                rows_to_delete.append(row)
        
        # Delete rows in reverse order to avoid index shifting
        for row in reversed(rows_to_delete):
            self.dataTable.removeRow(row)
        self.update_row_numbers(table)        
        QtWidgets.QMessageBox.information(self.Dialog, "Deleted", f"Deleted {len(rows_to_delete)} rows.")

    def filter_table_by_status(self, status):
        """
        Filters the table by the selected status.
        """
        filter_text = self.statusFilterMenu.currentText()  # Get the selected filter text
        matches_found = False

        for row in range(self.dataTable.rowCount()):
            status_item = self.dataTable.item(row, 11)  # Status is in the twelfth column (index 11)
            if status_item:
                status_value = status_item.text()
                if filter_text == "All" or status_value == filter_text:
                    self.dataTable.setRowHidden(row, False)  # Show the row
                    matches_found = True
                else:
                    self.dataTable.setRowHidden(row, True)  # Hide the row



        # Update row numbers after filtering
        self.update_row_numbers(self.dataTable)

    def search_table(self):
        """Searches the table for rows containing the search text."""
        search_text = self.searchBox.text().strip().lower()
        if not search_text:
            QtWidgets.QMessageBox.warning(self.Dialog, "Input Error", "Please enter text to search.")
            return

        matches_found = False
        for row in range(self.dataTable.rowCount()):
            match_found = False
            for col in range(self.dataTable.columnCount()):
                item = self.dataTable.item(row, col)
                if item and search_text in item.text().lower():
                    match_found = True
                    break
            self.dataTable.setRowHidden(row, not match_found)
            if match_found:
                matches_found = True

        if not matches_found:
            QtWidgets.QMessageBox.information(self.Dialog, "No Matches", "No rows found matching the search text.")

    def show_context_menu(self, pos, table):
        """
        Displays a context menu when the user right-clicks on the table.
        """
        menu = QtWidgets.QMenu(self.Dialog)
        
        # Add actions for copying specific columns
        copy_all_uids_action = QtWidgets.QAction("Copy All UIDs", self.Dialog)
        copy_all_names_action = QtWidgets.QAction("Copy All Names", self.Dialog)
        copy_all_passwords_action = QtWidgets.QAction("Copy All Passwords", self.Dialog)
        copy_all_emails_action = QtWidgets.QAction("Copy All Emails", self.Dialog)
        copy_all_rows_action = QtWidgets.QAction("Copy All Rows", self.Dialog)
        copy_checked_rows_action = QtWidgets.QAction("Copy Checked Rows", self.Dialog)
        delete_checked_rows_action = QtWidgets.QAction("Delete Checked Rows", self.Dialog)
        # Add "Check Live UID" actions
        check_live_all_uids_action = QtWidgets.QAction("Check Live All UIDs", self.Dialog)
        check_live_selected_uids_action = QtWidgets.QAction("Check Live UID by Selection", self.Dialog)
        # Connect actions to their respective functions
        copy_all_uids_action.triggered.connect(lambda: self.copy_column_data(table, 3))  # UID column
        copy_all_names_action.triggered.connect(lambda: self.copy_column_data(table, 2))  # Name column
        copy_all_passwords_action.triggered.connect(lambda: self.copy_column_data(table, 4))  # Password column
        copy_all_emails_action.triggered.connect(lambda: self.copy_column_data(table, 6))  # Email column
        copy_all_rows_action.triggered.connect(lambda: self.copy_all_rows(table))
        copy_checked_rows_action.triggered.connect(lambda: self.copy_checked_rows(table))
        delete_checked_rows_action.triggered.connect(lambda: self.delete_checked_rows(table))
        # Connect "Check Live UID" actions to their respective functions
        check_live_all_uids_action.triggered.connect(lambda: self.check_live_uids(table, check_all=True))
        check_live_selected_uids_action.triggered.connect(lambda: self.check_live_uids(table, check_all=False))


        # Add actions to the menu
        menu.addAction(copy_all_uids_action)
        menu.addAction(copy_all_names_action)
        menu.addAction(copy_all_passwords_action)
        menu.addAction(copy_all_emails_action)
        menu.addSeparator()
        menu.addAction(copy_all_rows_action)
        menu.addAction(copy_checked_rows_action)
        menu.addAction(delete_checked_rows_action)
        menu.addAction(check_live_all_uids_action)
        menu.addAction(check_live_selected_uids_action)
        # Show the context menu
        menu.exec_(table.viewport().mapToGlobal(pos))
        
    def check_live_uids(self, table, check_all=False):
        """
        Checks the live status of UIDs in the dataTable.
        Updates the status column to "Live" or "Die" based on the response.
        """
        # Determine which rows to check
        rows_to_check = []
        if check_all:
            # Check all rows if "Check Live All UIDs" is selected
            rows_to_check = list(range(table.rowCount()))
        else:
            # Check only selected rows if "Check Live UID by Selection" is selected
            for row in range(table.rowCount()):
                checkbox_item = table.item(row, 0)  # "Select" column
                if checkbox_item and checkbox_item.checkState() == QtCore.Qt.Checked:
                    rows_to_check.append(row)

        if not rows_to_check:
            QtWidgets.QMessageBox.warning(self.Dialog, "No Selection", "Please select at least one row to check.")
            return

        # Perform UID checks in a separate thread to avoid blocking the GUI
        thread = threading.Thread(target=self.perform_uid_checks, args=(table, rows_to_check))
        thread.start()

    def perform_uid_checks(self, table, rows_to_check):
        """
        Performs live UID checks for the specified rows.
        """
        for row in rows_to_check:
            uid_item = table.item(row, 3)  # UID is in the fourth column (index 3)
            if not uid_item:
                continue

            uid = uid_item.text().strip()
            if not uid:
                continue

            # Check if the UID is live or die
            status = self.checkLiveUid(uid)

            # Update the status column in the table
            status_item = QtWidgets.QTableWidgetItem(status)
            table.setItem(row, 11, status_item)  # Status is in the twelfth column (index 11)

            # Apply conditional formatting based on the status
            self.apply_conditional_formatting(table, row, status)


    def checkLiveUid(self, uid: str):
        """
        Validates a single Facebook UID using the profile picture endpoint.
        Returns "Live" if the UID is valid, otherwise "Die".
        """
        try:
            r = requests.get(f'https://graph2.facebook.com/v3.3/{uid}/picture?redirect=0', timeout=10)
            if 'height' in r.text and 'width' in r.text:
                return "Live"
            else:
                return "Die"
        except Exception as e:
            print(f"Error checking UID {uid}: {e}")
            return "Die"
        
    def copy_column_data(self, table, column):
        """
        Copies all data from the specified column of the given table to the clipboard.
        """
        clipboard = QtWidgets.QApplication.clipboard()
        data = []
        
        for row in range(table.rowCount()):
            item = table.item(row, column)
            if item and item.text():
                data.append(item.text())
        
        clipboard.setText("\n".join(data))  # Use newline as separator
        QtWidgets.QMessageBox.information(self.Dialog, "Copied", f"Copied {len(data)} items from column {column}.")

    def copy_all_rows(self, table):
        """
        Copies all rows from the given table to the clipboard as | separated values,
        excluding the "Select" and "No." columns.
        """
        clipboard = QtWidgets.QApplication.clipboard()
        data = []

        for row in range(table.rowCount()):
            row_data = []
            # Start from column 2 to exclude "Select" and "No." columns
            for col in range(2, table.columnCount()):
                item = table.item(row, col)
                if item and item.text():
                    row_data.append(item.text())
                else:
                    row_data.append("")  # Add empty string for missing data
            data.append("|".join(row_data))  # Use | as the delimiter

        clipboard.setText("\n".join(data))  # Use newline as row separator
        QtWidgets.QMessageBox.information(self.Dialog, "Copied", f"Copied {len(data)} rows.")

    def copy_checked_rows(self, table):
        """
        Copies only the rows where the checkbox in the "Select" column is checked,
        using | as the delimiter and excluding the "Select" and "No." columns.
        """
        clipboard = QtWidgets.QApplication.clipboard()
        data = []

        for row in range(table.rowCount()):
            checkbox_item = table.item(row, 0)  # "Select" column
            if checkbox_item and checkbox_item.checkState() == QtCore.Qt.Checked:
                row_data = []
                # Start from column 2 to exclude "Select" and "No." columns
                for col in range(2, table.columnCount()):
                    item = table.item(row, col)
                    if item and item.text():
                        row_data.append(item.text())
                    else:
                        row_data.append("")  # Add empty string for missing data
                data.append("|".join(row_data))  # Use | as the delimiter

        clipboard.setText("\n".join(data))  # Use newline as row separator
        QtWidgets.QMessageBox.information(self.Dialog, "Copied", f"Copied {len(data)} checked rows.")

    def update_row_numbers(self, table):
        """
        Updates the "No." column in the table to reflect the current row order.
        Only visible rows are numbered sequentially.
        """
        visible_row_count = 0  # Counter for visible rows
        for row in range(table.rowCount()):
            if not table.isRowHidden(row):  # Check if the row is visible
                visible_row_count += 1

                # Update the row number in the second column (index 1)
                row_number_item = QtWidgets.QTableWidgetItem(str(visible_row_count))
                row_number_item.setTextAlignment(QtCore.Qt.AlignCenter)  # Center-align the text
                table.setItem(row, 1, row_number_item)

                # Reapply conditional formatting based on the status
                status_item = table.item(row, 11)  # Status is in the twelfth column (index 11)
                if status_item:
                    status = status_item.text()
                    self.apply_conditional_formatting(table, row, status)

    

    def get_icon_path(self, icon_name):
            """Helper function to get the absolute path of an icon/image file."""
            current_dir = os.path.dirname(os.path.abspath(__file__))
            return os.path.join(current_dir, "img", icon_name)
        


    def generate_random_names(self):
        try:
            # Predefined lists of Thai first names and last names
            first_names = [
                "ธานี", "ปรามานัต", "พระอานนท์", "ธนวัฒน์", "ชัยวัฒน์", 
                "สุริยา", "กิตติศักดิ์", "พิชญ์", "วิษณุ", "จตุพร"
            ]
            last_names = [
                "สุทัศนะจินดา", "แก้วมณี", "พญาวัง", "ศรีสุข", "แสงธรรม", 
                "ชูชาติ", "วงศ์วาน", "ศักดิ์สิทธิ์", "สมบูรณ์", "เทพา"
            ]

            # Generate 10 random names
            generated_names = [
                f"{random.choice(first_names)} {random.choice(last_names)}"
                for _ in range(10)
            ]

            # Save the generated names to a text file
            with open(".\\data\\names.txt", "a", encoding="utf-8") as file:
                for name in generated_names:
                    file.write(name + "\n")

            QtWidgets.QMessageBox.information(None, "Success", f"{len(generated_names)} names saved to file!")
        except Exception as e:
            QtWidgets.QMessageBox.critical(None, "Error", f"Failed to save names: {str(e)}")

    def generate_emails_and_passwords(self):
        try:
            # Get user-provided email format and password
            email_format = self.emailFormatInput.text().strip()
            password = self.passwordInput.text().strip()

            if not email_format or "{}" not in email_format:
                QtWidgets.QMessageBox.warning(None, "Invalid Input", "Please provide a valid email format with '{}'.")
                return

            if not password:
                QtWidgets.QMessageBox.warning(None, "Invalid Input", "Please provide a password.")
                return

            # Function to generate a random email based on the user's format
            def generate_random_email():
                suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
                return email_format.format(suffix)

            # Generate 10 random emails and passwords
            emails_and_passwords = [(generate_random_email(), password) for _ in range(1000)]

            # Save the generated emails and passwords to a text file
            with open(".\\data\\mail.txt", "a", encoding="utf-8") as file:
                for email, password in emails_and_passwords:
                    file.write(f"{email}|{password}\n")

            QtWidgets.QMessageBox.information(None, "Success", f"{len(emails_and_passwords)} emails and passwords saved to file!")
        except Exception as e:
            QtWidgets.QMessageBox.critical(None, "Error", f"Failed to save emails and passwords: {str(e)}")


    def startButtonClicked(self):
        # Change button appearance temporarily
        self.startButton.setStyleSheet(
            "color: white; background-color: green; border: 1px solid black; font-family: 'Arial'; font-size: 16px; font-weight: bold;"
        )
        QtCore.QTimer.singleShot(200, self.resetStartButtonStyle)  # Reset after 200ms

    def stopButtonClicked(self):
        # Change button appearance temporarily
        self.stopButton.setStyleSheet(
            "color: white; background-color: red; border: 1px solid black; font-family: 'Arial'; font-size: 16px; font-weight: bold;"
        )
        QtCore.QTimer.singleShot(200, self.resetStopButtonStyle)  # Reset after 200ms

    def resetStartButtonStyle(self):
        self.startButton.setStyleSheet(
            "color: black; background-color: white; border: 1px solid black; font-family: 'Arial'; font-size: 16px; font-weight: bold;"
        )

    def resetStopButtonStyle(self):
        self.stopButton.setStyleSheet(
            "color: black; background-color: white; border: 1px solid black; font-family: 'Arial'; font-size: 16px; font-weight: bold;"
        )


    def loadNamesFromFile(self):
        try:
            # Use a direct relative path
            fileName = ".\\data\\names.txt"
            with open(fileName, "r", encoding="utf-8") as file:
                self.namesList = file.read().splitlines()
            print(f"Loaded {len(self.namesList)} names from {fileName}")
        except FileNotFoundError:
            print(f"Error: The file {fileName} was not found.")
        except Exception as e:
            print(f"Error: {e}")

    def loadmailandpassmailFromFile(self):
        try:
            # Use a direct relative path
            filemailandpass = ".\\data\\mail.txt"
            with open(filemailandpass, "r", encoding="utf-8") as file:
                self.mailList = [line.strip().split('|') for line in file.readlines() if line.strip()]
            
            # Deduplicate the mailList
            self.mailList = list(set(tuple(pair) for pair in self.mailList))  # Convert to tuples for set compatibility
            self.mailList = [list(pair) for pair in self.mailList]  # Convert back to lists
            
            print(f"Loaded {len(self.mailList)} mail and password pairs from {filemailandpass}")
        except FileNotFoundError:
            print(f"Error: The file {filemailandpass} was not found.")
        except Exception as e:
            print(f"Error: {e}")

    def togglePasswordField(self):
        """Enable or disable the custom password field based on the selected radio button."""
        self.customPasswordLineEdit.setEnabled(self.radio_custom_password.isChecked())

    def startProcess(self):
        # Load Names and Emails
        self.loadNamesFromFile()
        self.loadmailandpassmailFromFile()

        # Check if mailList is populated
        if not self.mailList:
            QtWidgets.QMessageBox.critical(None, "Error", "No emails loaded. Please check mail.txt or generate new emails.")
            return

        self.workers = []
        self.threads = []
        self.stop_flags = []  # Initialize the stop flags list

        gender_option = self.genderCombo.currentText()
        random_phone = self.randomPhoneCheckbox.isChecked()
        use_random_password = self.radio_random_password.isChecked()  # Use radio button state
        custom_password = self.customPasswordLineEdit.text() if not use_random_password else ""

        # Get the selected verification option
        account_no_verify = self.radio_no_verify.isChecked()
        account_fullverify = self.radio_full_verify.isChecked()

        # Create a shared email queue and lock
        self.email_queue = self.mailList[:]
        self.lock = threading.Lock()
        # Determine the selected name source
        if self.radio_random_name.isChecked():
            name_source = "Random"
        elif self.radio_english_name.isChecked():
            name_source = "English"
        elif self.radio_thai_name.isChecked():
            name_source = "Thai"
        elif self.radio_khmer_name.isChecked():
            name_source = "Khmer"
        elif self.radio_chinese_name.isChecked():
            name_source = "Chinese"
        elif self.radio_file_name.isChecked():
            name_source = "File"
        else:
            name_source = "Random"  # Default fallback
            
        for i in range(self.threadsInput.value()):
            stop_flag = threading.Event()  # Create a stop flag for each worker
            self.stop_flags.append(stop_flag)  # Store the stop flag

            worker = Worker(
                i,
                self.namesList,
                self.delayInput.value(),
                self.stopInput.value(),
                gender_option,
                random_phone,
                use_random_password,
                custom_password,
                self.email_queue,
                self.lock,
                account_no_verify,  # Pass radio button state
                account_fullverify,  # Pass radio button state
                name_source,
                output_lock=self.output_lock,
            )

            thread = QtCore.QThread()
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.finished.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            worker.progress.connect(self.updateTable)

            self.workers.append(worker)
            self.threads.append(thread)
            thread.start()
        

    def stopProcess(self):
        """
        Stops all active threads and workers gracefully.
        """
        # Check if workers and threads are initialized
        if not hasattr(self, 'workers') or not hasattr(self, 'threads'):
            print("No processing threads are initialized.")
            return

        # Use a thread-safe lock to prevent race conditions
        with self.lock:
            if not self.workers and not self.threads:
                print("No active workers or threads to stop.")
                return

            # Check if stop flags are initialized
            if not hasattr(self, 'stop_flags') or not self.stop_flags:
                print("No stop flags initialized.")
                return

            # Set all stop flags to signal workers to stop
            for i, stop_flag in enumerate(self.stop_flags):
                stop_flag.set()
                print(f"Stop flag set for worker {i}.")

            # Stop all workers
            for i, worker in enumerate(self.workers):
                try:
                    worker.stop()  # Call the worker's stop method if it exists
                    print(f"Worker {i} stopped successfully.")
                except Exception as e:
                    print(f"Error stopping worker {i}: {e}")

            # Stop all threads
            for i, thread in enumerate(self.threads):
                try:
                    if thread.isRunning():
                        thread.quit()
                        thread.wait(2000)  # Wait up to 2 seconds for the thread to stop
                        if thread.isRunning():
                            print(f"Thread {i} did not stop within 2 seconds.")
                        else:
                            print(f"Thread {i} stopped successfully.")
                except RuntimeError as e:
                    print(f"Error stopping thread {i}: {e}")

            print("Stopped all active threads and workers (if any).")




    def updateTable(self, name, uid, password, phone_number, email, cookies, gender, birthdate, twofa, status):
        """
        Inserts data into the table widget and writes data to the appropriate output file.
        """
        # Get the current row position
        rowPosition = self.tableWidget.rowCount()
        self.tableWidget.insertRow(rowPosition)

        # Add a checkbox in the first column
        checkbox_item = QtWidgets.QTableWidgetItem()
        checkbox_item.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
        checkbox_item.setCheckState(QtCore.Qt.Unchecked)  # Default to unchecked
        self.tableWidget.setItem(rowPosition, 0, checkbox_item)

        # Add the row number in the second column
        row_number_item = QtWidgets.QTableWidgetItem(str(rowPosition + 1))  # Row numbers start from 1
        row_number_item.setTextAlignment(QtCore.Qt.AlignCenter)  # Center-align the text
        self.tableWidget.setItem(rowPosition, 1, row_number_item)

        # Add the remaining data to subsequent columns
        self.tableWidget.setItem(rowPosition, 2, QtWidgets.QTableWidgetItem(name))
        self.tableWidget.setItem(rowPosition, 3, QtWidgets.QTableWidgetItem(uid))
        self.tableWidget.setItem(rowPosition, 4, QtWidgets.QTableWidgetItem(password))
        self.tableWidget.setItem(rowPosition, 5, QtWidgets.QTableWidgetItem(phone_number))
        self.tableWidget.setItem(rowPosition, 6, QtWidgets.QTableWidgetItem(email))
        self.tableWidget.setItem(rowPosition, 7, QtWidgets.QTableWidgetItem(cookies))
        self.tableWidget.setItem(rowPosition, 8, QtWidgets.QTableWidgetItem(gender))
        self.tableWidget.setItem(rowPosition, 9, QtWidgets.QTableWidgetItem(birthdate))
        self.tableWidget.setItem(rowPosition, 10, QtWidgets.QTableWidgetItem(twofa))
        self.tableWidget.setItem(rowPosition, 11, QtWidgets.QTableWidgetItem(status))
        #self.update_row_numbers(self.tableWidget)
        # Apply conditional formatting based on status
        if status == "Successful":
            row_color = "#d4edb6"  # Green
            self.successful_count += 1
        elif status == "Fully Verified":
            row_color = "#d4edb6"  # Blue
            self.fully_verified_count += 1
        elif status == "Checkpoint":
            row_color = "#FFC107"  # Yellow
            self.checkpoint_count += 1
        elif status == "Fail":
            row_color = "#ffadad"  # Red
            self.fail_count += 1
        else:
            row_color = "#607D8B"  # Gray (default)

        # Set the background color for the entire row
        for col in range(self.tableWidget.columnCount()):
            item = self.tableWidget.item(rowPosition, col)
            if item:
                item.setBackground(QtGui.QColor(row_color))

        # Update total count and refresh status counters
        self.total_count += 1
        self.updateStatusCounts()

        try:
            # Generate a timestamp for the current date and time
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Format: YYYY-MM-DD HH:MM:SS

            # Ensure the output directory exists
            output_directory = self.outputDirectoryInput.text().strip() or ".\\output"
            os.makedirs(output_directory, exist_ok=True)

            # Determine the file name based on the status
            if status == "Successful":
                file_name = os.path.join(output_directory, "account_noverify.txt")
            elif status == "Fully Verified":
                file_name = os.path.join(output_directory, "account_fullverify.txt")
            elif status == "Checkpoint":
                file_name = os.path.join(output_directory, "account_checkpoint.txt")
            else:  # Default to "Fail" for all other statuses
                file_name = os.path.join(output_directory, "account_fail.txt")

            # Auto-create the file if it doesn't exist
            if not os.path.exists(file_name):
                with open(file_name, "w", encoding="utf-8") as file:
                    file.write("")  # Create an empty file

            # Write the data line to the appropriate file
            data_line = (
                f"{name}|{uid}|{password}|{phone_number}|{email}|{cookies}|{gender}|{birthdate}|{twofa}|{status}|{timestamp}\n"
            )
            # Use the output lock to ensure thread-safe writes
            with self.output_lock:
                with open(file_name, "a", encoding="utf-8") as file:
                    file.write(data_line)

            print(f"Data saved to {file_name} with timestamp: {timestamp}")
        except Exception as e:
            print(f"Error saving data to file: {e}")

    def select_output_directory(self):
        """
        Opens a directory selection dialog and updates the output directory input field.
        """
        options = QtWidgets.QFileDialog.Options()
        options |= QtWidgets.QFileDialog.ShowDirsOnly  # Restrict to directories only
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            None,
            "Select Output Directory",
            "",
            options=options
        )
        if directory:
            self.outputDirectoryInput.setText(directory)  # Update the input field with the selected directory
            
    def open_output_folder(self):
        """
        Opens the output folder in the system's file explorer.
        If a custom directory is selected via the Browse button, it opens that directory.
        Otherwise, it defaults to ".\\output".
        """
        try:
            # Get the directory from the input field or default to ".\\output"
            selected_directory = self.outputDirectoryInput.text().strip()
            if selected_directory:
                output_dir = os.path.abspath(selected_directory)
            else:
                output_dir = os.path.abspath(".\\output")

            # Ensure the directory exists
            if os.path.exists(output_dir):
                os.startfile(output_dir)  # Open the directory in the file explorer
            else:
                QtWidgets.QMessageBox.warning(None, "Error", f"The directory '{output_dir}' does not exist.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(None, "Error", f"Failed to open output folder: {str(e)}")

    def updateStatusCounts(self):
        """Update the status counters label with different colors."""
        self.statusCountsLabel.setText(
            f"""
            <html>
            <body>
                <span style="color: #FFFFFF; font-family: 'Segoe UI', sans-serif; font-weight: bold;">Total: {self.total_count}</span>  <!-- White -->
                <span style="color: #4CAF50; font-family: 'Segoe UI', sans-serif; font-weight: bold;">No Verify: {self.successful_count}</span>  <!-- Green -->
                <span style="color: #2196F3; font-family: 'Segoe UI', sans-serif; font-weight: bold;">Fully Verified: {self.fully_verified_count}</span>  <!-- Blue -->
                <span style="color: #FFC107; font-family: 'Segoe UI', sans-serif; font-weight: bold;">Checkpoint: {self.checkpoint_count}</span>  <!-- Yellow -->
                <span style="color: #FF5252; font-family: 'Segoe UI', sans-serif; font-weight: bold;">Fail: {self.fail_count}</span>  <!-- Red -->
            </body>
            </html>
            """
        )


if __name__ == "__main__":
    app = QApplication([])

    Dialog = QtWidgets.QDialog()
    ui = Ui_Dialog()
    ui.setupUi(Dialog)

    Dialog.show()
    sys.exit(app.exec_())