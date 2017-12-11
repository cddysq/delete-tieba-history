from selenium import webdriver,common
import time
import re
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
import urllib.request
from selenium.webdriver.common.action_chains import ActionChains 

def login(username,password):
    print("Spider started")
    urlusername=urllib.request.quote(username) 
    driver.get("http://tieba.baidu.com/home/main?un="+urlusername+"&fr=home")
    driver.find_element_by_class_name("u_login").click()
    time.sleep(0.5)
    driver.find_element_by_id("TANGRAM__PSP_10__userName").send_keys(username)
    driver.find_element_by_id("TANGRAM__PSP_10__password").send_keys(password)
    driver.find_element_by_id("TANGRAM__PSP_10__submit").click()
    time.sleep(3)

def my_tie_collector():  
    driver.get("http://tieba.baidu.com/i/i/my_tie")
    listOfLinks=list()
    listOfElements=driver.find_elements_by_class_name("thread_title")
    for i in range(0,len(listOfElements)-1):
        listOfLinks.append(listOfElements[i].get_attribute("href"))

    driver.get("http://tieba.baidu.com/i/i/my_tie?&pn=2")  #注意每天限制30贴，所以最多前两页就足够了
    listOfElements=driver.find_elements_by_class_name("thread_title")
    for i in range(0,len(listOfElements)-1):
        listOfLinks.append(listOfElements[i].get_attribute("href"))

    print("Links of Tie Collected")
    return listOfLinks

def my_reply_collector():
    driver.get("http://tieba.baidu.com/i/i/my_reply")
    listOfLinks=list()
    listOfElements=driver.find_elements_by_class_name("for_reply_context")
    for i in range(0,len(listOfElements)-1):
        listOfLinks.append(listOfElements[i].get_attribute("href"))

    driver.get("http://tieba.baidu.com/i/i/my_reply?&pn=2")  #同上
    listOfElements=driver.find_elements_by_class_name("for_reply_context")
    for i in range(0,len(listOfElements)-1):
        listOfLinks.append(listOfElements[i].get_attribute("href"))

    print("Links of Reply Collected")
    return listOfLinks

def deleter_tie(listOfLinks):
    print("Now Deleting")
    for i in range(0,len(listOfLinks)-1):
        try:
            driver.get(listOfLinks[i])
            element=driver.find_element_by_class_name("p_post_del_my")
            driver.execute_script("arguments[0].scrollIntoView(false);", element)
            element.click()
            time.sleep(0.1)                  
            driver.find_element_by_class_name("dialogJanswers").find_element_by_tag_name("input").click()
            print("Deleted")
        except common.exceptions.NoSuchElementException:
            print("Fail to find the element") #古老版本匿名,或者隐藏帖子没有删除按钮

def deleter_follows():
    while True:
        driver.get("http://tieba.baidu.com/i/i/concern")
        try:
            driver.find_element_by_class_name("btn_unfollow").click()
            driver.find_element_by_class_name("dialogJbtn").click()
            time.sleep(0.5)
        except common.exceptions.NoSuchElementException:
            print("Follows has been all deleted")
            break
            
def deleter_fans():
    while True:
        driver.get("http://tieba.baidu.com/i/i/fans")
        try:
            element=driver.find_element_by_class_name("name")
            ActionChains(driver).move_to_element(element).perform() #移动到名字否则取消关注不会出现
            driver.find_element_by_id("add_blacklist_btn").click()
            driver.find_element_by_class_name("dialogJbtn").click()
            time.sleep(0.5)
        except common.exceptions.NoSuchElementException:
            print("Fans has been all deleted")
            break   
            
def deleter_BaIFollow(): #使用此功能需打开图片显示
    driver.get("http://tieba.baidu.com/i/i/forum")
    driver.find_element_by_class_name("pm_i_know").click()
    while True:
        try:
            driver.find_element_by_class_name("pt").click()
            driver.find_element_by_class_name("dialogJbtn").click()
            time.sleep(0.5)
        except common.exceptions.NoSuchElementException:
            print("BaIFollows has been all deleted")
            break
            
def Start_with_Chrome():
    chrome_options = webdriver.ChromeOptions()
    prefs = {"profile.managed_default_content_settings.images":2} #不加载图片 若注释掉这行和下一行即加载图片
    chrome_options.add_experimental_option("prefs",prefs)
    driver=webdriver.Chrome(chrome_options=chrome_options)
    return driver

driver=Start_with_Chrome()
login("Here is your username","Here is your password")
deleter_tie(my_reply_collector()) #Or my_tie_collector()
deleter_fans()
deleter_follows()
print("All done")
