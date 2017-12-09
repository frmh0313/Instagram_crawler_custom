from __future__ import division

import argparse
import codecs
from collections import defaultdict
import json
import os
import re
import sys
import time
try:
    from urlparse import urljoin
    from urllib import urlretrieve
except ImportError:
    from urllib.parse import urljoin
    from urllib.request import urlretrieve

import requests
import selenium
from selenium import webdriver
from selenium.webdriver.firefox.firefox_binary import FirefoxBinary
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import json

# HOST
HOST = 'http://www.instagram.com'

# SELENIUM CSS SELECTOR
CSS_LOAD_MORE = "a._1cr2e._epyes"
#CSS_RIGHT_ARROW = "a[class='_de018 coreSpriteRightPaginationArrow']"
CSS_RIGHT_ARROW = "a[class='_3a693 coreSpriteRightPaginationArrow']"
# FIREFOX_FIRST_POST_PATH = "//div[contains(@class, '_8mlbc _vbtk2 _t5r8b')]" ORIGINAL
FIREFOX_FIRST_POST_PATH = "//div[contains(@class, '_mck9w _gvoze _f2mse')]"
TIME_TO_CAPTION_PATH = "../../../div/ul/li/span"

# FOLLOWERS/FOLLOWING RELATED
CSS_EXPLORE = "a[href='/explore/']"
CSS_LOGIN = "a[href='/accounts/login/']"
CSS_FOLLOWERS = "a[href='/{}/followers/']"
CSS_FOLLOWING = "a[href='/{}/following/']"
FOLLOWER_PATH = "//div[contains(text(), 'Followers')]"
FOLLOWING_PATH = "//div[contains(text(), 'Following')]"

# JAVASCRIPT COMMANDS
SCROLL_UP = "window.scrollTo(0, 0);"
SCROLL_DOWN = "window.scrollTo(0, document.body.scrollHeight);"

class url_change(object):
    """
        Used for caption scraping
    """
    def __init__(self, prev_url):
        self.prev_url = prev_url

    def __call__(self, driver):
        return self.prev_url != driver.current_url

class InstagramCrawler(object):
    """
        Crawler class
    """
    def __init__(self, headless=True, firefox_path=None):
        if headless:
            print("headless mode on")
            self._driver = webdriver.PhantomJS()
        else:
            # credit to https://github.com/SeleniumHQ/selenium/issues/3884#issuecomment-296990844
            # for headless mode of firefox
            binary = FirefoxBinary(firefox_path)
            # binary.add_command_line_options(['headless'])
            self._driver = webdriver.Firefox(firefox_binary=binary)

            # if __name__ == '__main__':
            #     self._driver = webdriver.Firefox(firefox_options=('-headless'))
                # binary = FirefoxBinary(firefox_path)
                # binary = binary.add_command_line_options(['-headless'])
                # self._driver = webdriver.Firefox(firefox_binary=binary)
            # self._driver = webdriver.Firefox(firefox_binary=binary, firefox_options='-headless')
            # self._driver = webdriver.Firefox(executable_path=firefox_path, firefox_options=['-headless'])


        self._driver.implicitly_wait(10)
        self.data = defaultdict(list)

    def login(self, authentication=None):
        """
            authentication: path to authentication json file
        """
        self._driver.get(urljoin(HOST, "accounts/login/"))

        if authentication:
            print("Username and password loaded from {}".format(authentication))
            with open(authentication, 'r') as fin:
                auth_dict = json.loads(fin.read())
            # Input username
            username_input = WebDriverWait(self._driver, 5).until(
                EC.presence_of_element_located((By.NAME, 'username'))
            )
            username_input.send_keys(auth_dict['username'])
            # Input password
            password_input = WebDriverWait(self._driver, 5).until(
                EC.presence_of_element_located((By.NAME, 'password'))
            )
            password_input.send_keys(auth_dict['password'])
            # Submit
            password_input.submit()
        else:
            print("Type your username and password by hand to login!")
            print("You have a minute to do so!")

        print("")
        WebDriverWait(self._driver, 60).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, CSS_EXPLORE))
        )

    def quit(self):
        self._driver.quit()

    def crawl(self, dir_prefix, query, crawl_type, number, caption, authentication):
        print("dir_prefix: {}, query: {}, crawl_type: {}, number: {}, caption: {}, authentication: {}"
              .format(dir_prefix, query, crawl_type, number, caption, authentication))

        if crawl_type == "photos":
            # Browse target page
            self.browse_target_page(query)
            # Scroll down until target number photos is reached
            #num_of_posts = self.scroll_to_num_of_posts(number)
            num_of_posts = self.num_of_posts()
            # Scrape photo links
            # self.scrape_photo_links(number, is_hashtag=query.startswith("#")) # Do not download image
            # Scrape captions if specified
            if caption is True:
                # self.click_and_scrape_captions(number, query, dir_prefix)
                self.click_and_scrape_captions(num_of_posts, query, dir_prefix)

        elif crawl_type in ["followers", "following"]:
            # Need to login first before crawling followers/following
            print("You will need to login to crawl {}".format(crawl_type))
            self.login(authentication)

            # Then browse target page
            assert not query.startswith(
                '#'), "Hashtag does not have followers/following!"
            self.browse_target_page(query)
            # Scrape captions
            self.scrape_followers_or_following(crawl_type, query, number)
        else:
            print("Unknown crawl type: {}".format(crawl_type))
            self.quit()
            return
        # Save to directory
        print("Saving...")
        # self.download_and_save(dir_prefix, query, crawl_type)

        # Quit driver
        print("Quitting driver...")
        self.quit()

    def browse_target_page(self, query):
        # Browse Hashtags
        if query.startswith('#'):
            relative_url = urljoin('explore/tags/', query.strip('#'))
        else:  # Browse user page
            relative_url = query

        target_url = urljoin(HOST, relative_url)

        self._driver.get(target_url)

    def num_of_posts(self):
        num_info = re.search(r'\], "count": \d+',
                             self._driver.page_source).group()
        num_of_posts = int(re.findall(r'\d+', num_info)[0])
        return num_of_posts

    def scroll_to_num_of_posts(self, number, num_of_posts):
        print("posts: {}, number: {}".format(num_of_posts, number))
        number = number if number < num_of_posts else num_of_posts

        # scroll page until reached
        loadmore = WebDriverWait(self._driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, CSS_LOAD_MORE))
        )
        loadmore.click()

        num_to_scroll = int((number - 12) / 12) + 1
        for i in range(num_to_scroll):
            print("Scrolls: {}/{}".format(i, num_to_scroll))
            self._driver.execute_script(SCROLL_DOWN)
            time.sleep(0.2)
            self._driver.execute_script(SCROLL_UP)
            time.sleep(0.2)
        return num_of_posts

    def scrape_photo_links(self, number, is_hashtag=False):
        print("Scraping photo links...")
        encased_photo_links = re.finditer(r'src="([https]+:...[\/\w \.-]*..[\/\w \.-]*'
                                          r'..[\/\w \.-]*..[\/\w \.-].jpg)', self._driver.page_source)

        photo_links = [m.group(1) for m in encased_photo_links]

        print("Number of photo_links: {}".format(len(photo_links)))

        begin = 0 if is_hashtag else 1

        self.data['photo_links'] = photo_links[begin:number + begin]

    def click_and_scrape_captions(self, number, query, dir_prefix):
        print("Scraping captions...")
        num_captions_in_file = 1000

        dir_name = query.lstrip(
            '#') + '.hashtag' if query.startswith('#') else query

        dir_path = os.path.join(dir_prefix, dir_name)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

        for post_num in range(number):
            captions = []
            sys.stdout.write("\033[F")
            print("Scraping captions {} / {}".format(post_num+1,number))
            if post_num == 0:  # Click on the first post
                # Chrome
                #self._driver.find_element_by_class_name('_ovg3g').click()
                self._driver.find_element_by_xpath(
                    FIREFOX_FIRST_POST_PATH).click()

                if number != 1:  #
                    trying = True
                    wait = 0
                    while trying:
                        try:
                            WebDriverWait(self._driver, wait).until(
                                EC.presence_of_element_located(
                                    (By.CSS_SELECTOR, CSS_RIGHT_ARROW)
                                )
                            )
                        except TimeoutException:
                            print("Timeout in post_num 0. Trying again")
                            wait += 0.1
                            continue
                        else:
                            trying = False
                            wait = 0

            elif number != 1:  # Click Right Arrow to move to next post
                trying = True
                wait = 0
                while trying:
                    try:
                        url_before = self._driver.current_url
                        self._driver.find_element_by_css_selector(
                            CSS_RIGHT_ARROW).click()
                        WebDriverWait(self._driver, wait).until(
                            url_change(url_before))
                    except TimeoutException:
                        print("Time out in caption scraping at number {}".format(post_num))
                        print("Trying again")
                        wait += 0.1
                        continue
                    except NoSuchElementException as e:
                        print(e)
                        print("Try again")
                    else:
                        trying = False
                        wait = 0


            # Parse caption
            # + Parse date
            trying = True
            wait = 0
            while trying:
                try:
                    time_element = WebDriverWait(self._driver, wait).until(
                        EC.presence_of_element_located((By.TAG_NAME, "time"))
                    )
                    datetime = time_element.get_attribute('datetime')
                    date_title = time_element.get_attribute('title')
                    caption = time_element.find_element_by_xpath(
                        TIME_TO_CAPTION_PATH).text
                    caption_date = { 'count': post_num+1, 'caption':caption, 'datetime': datetime, 'datetime_title':date_title }
                    # caption = {}
                    # caption['text'] = time_element.find_element_by_xpath(
                    #     TIME_TO_CAPTION_PATH).text
                    # caption['datetime'] = datetime
                    # caption['datetime_title'] = date_title
                except TimeoutException:
                    print("Time exception. Trying again")
                except NoSuchElementException:  # Forbidden
                    print("Caption not found in the {} photo".format(post_num))
                    caption = ""
                    wait += 0.1
                    break
                except StaleElementReferenceException:
                    print("StaleElement. Try to refresh")
                    while trying:
                        try:
                            url_before = self._driver.current_url
                            self._driver.find_element_by_css_selector(
                                CSS_RIGHT_ARROW).click()
                            WebDriverWait(self._driver, wait).until(
                                url_change(url_before))
                        except TimeoutException:
                            print("Time out in caption scraping at number {}".format(post_num))
                            print("Trying again")
                            wait += 0.1
                            continue
                        else:
                            trying = False
                            wait = 0
                else:
                    trying = False
                    wait = 0
            captions.append(caption_date)
            self.data['captions'].extend(captions)
            count = post_num + 1
            if count % num_captions_in_file == 0:
                filename = str(count) +'.txt'
                filepath = os.path.join(dir_path, filename)
                print('file {}'.format(filename), 'writing')

                caption_result = []
                for caption in self.data['captions']:
                    caption_result.append({'count': caption['count'],
                                           'caption': caption['caption'],
                                           'datetime': caption['datetime'],
                                           'datetime_title': caption['datetime_title']})
                    json_object = json.dumps(caption_result, ensure_ascii=False, indent=4)
                    with codecs.open(filepath, 'w', encoding='utf8') as fout:
                        json.dump(json_object, fout, ensure_ascii=False)
                self.data['captions'] = []
            if count == number:
                filename = str(count) + '.txt'
                filepath = os.path.join(dir_path, filename)
                print('file {}'.format(filename), 'writing')

                caption_result = []
                for caption in self.data['captions']:
                    caption_result.append({'count': caption['count'],
                                           'caption': caption['caption'],
                                           'datetime': caption['datetime'],
                                           'datetime_title': caption['datetime_title']})
                    json_object = json.dumps(caption_result, ensure_ascii=False, indent=4)
                    with codecs.open(filepath, 'w', encoding='utf8') as fout:
                        json.dump(json_object, fout, ensure_ascii=False)
            # captions.append(datetime)
            # captions.append(date_title)

    def scrape_followers_or_following(self, crawl_type, query, number):
        print("Scraping {}...".format(crawl_type))
        if crawl_type == "followers":
            FOLLOW_ELE = CSS_FOLLOWERS
            FOLLOW_PATH = FOLLOWER_PATH
        elif crawl_type == "following":
            FOLLOW_ELE = CSS_FOLLOWING
            FOLLOW_PATH = FOLLOWING_PATH

        # Locate follow list
        follow_ele = WebDriverWait(self._driver, 5).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, FOLLOW_ELE.format(query)))
        )

        # when no number defined, check the total items
        if number is 0:
            number = int(filter(str.isdigit, str(follow_ele.text)))
            print("getting all " + str(number) + " items")

        # open desired list
        follow_ele.click()

        title_ele = WebDriverWait(self._driver, 5).until(
            EC.presence_of_element_located(
                (By.XPATH, FOLLOW_PATH))
        )
        List = title_ele.find_element_by_xpath(
            '..').find_element_by_tag_name('ul')
        List.click()

        # Loop through list till target number is reached
        num_of_shown_follow = len(List.find_elements_by_xpath('*'))
        while len(List.find_elements_by_xpath('*')) < number:
            element = List.find_elements_by_xpath('*')[-1]
            # Work around for now => should use selenium's Expected Conditions!
            try:
                element.send_keys(Keys.PAGE_DOWN)
            except Exception as e:
                time.sleep(0.1)

        follow_items = []
        for ele in List.find_elements_by_xpath('*')[:number]:
            follow_items.append(ele.text.split('\n')[0])

        self.data[crawl_type] = follow_items

    def download_and_save(self, dir_prefix, query, crawl_type):
        # Check if is hashtag
        dir_name = query.lstrip(
            '##') + '.hashtag' if query.startswith('#') else query

        dir_path = os.path.join(dir_prefix, dir_name)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

        print("Saving to directory: {}".format(dir_path))

        # Save Photos
        for idx, photo_link in enumerate(self.data['photo_links'], 0):
            sys.stdout.write("\033[F")
            print("Downloading {} images to ".format(idx + 1))
            # Filename
            _, ext = os.path.splitext(photo_link)
            filename = str(idx) + ext
            filepath = os.path.join(dir_path, filename)
            # Send image request
            urlretrieve(photo_link, filepath)

        # Save Captions
        caption_result = []
        for idx, caption in enumerate(self.data['captions'], 0):

            filename = 'caption_and_date.txt'
            filepath = os.path.join(dir_path, filename)

            # with codecs.open(filepath, 'w', encoding='utf-8') as fout:
            #     fout.write(caption + '\n')file_start

            # caption_result['comments'] = {'caption':caption['caption'], 'datetime':caption['datetime'], 'datetime_title':caption['datetime_title']}


            caption_result.append({'count': caption['count'],
                                   'caption':caption['caption'],
                                   'datetime':caption['datetime'],
                                   'datetime_title':caption['datetime_title']})
            json_object = json.dumps(caption_result, ensure_ascii=False, indent=4)

            with codecs.open(filepath, 'w', encoding='utf8') as fout:
                # fout.write(json_object)
                json.dump(json_object, fout, ensure_ascii=False)

            # with codecs.open(filepath, 'a', encoding='utf8') as fout:
            #     fout.write(caption['caption']+'\n')
            #     fout.write('\t\t\n\t\t')
            #     fout.write(caption['datetime'])
            #     fout.write('\t\t\n\t\t')
            #     fout.write(caption['datetime_title'])
            #     fout.write('\n')
        #


        # Save followers/following
        filename = crawl_type + '.txt'
        filepath = os.path.join(dir_path, filename)
        if len(self.data[crawl_type]):
            with codecs.open(filepath, 'w', encoding='utf-8') as fout:
                for fol in self.data[crawl_type]:
                    fout.write(fol + '\n')


def main():
    #   Arguments  #
    parser = argparse.ArgumentParser(description='Instagram Crawler')
    parser.add_argument('-d', '--dir_prefix', type=str,
                        default='./data/', help='directory to save results')
    parser.add_argument('-q', '--query', type=str, default='instagram',
                        help="target to crawl, add '#' for hashtags")
    parser.add_argument('-t', '--crawl_type', type=str,
                        default='photos', help="Options: 'photos' | 'followers' | 'following'")
    parser.add_argument('-n', '--number', type=int, default=0,
                        help='Number of posts to download: integer')
    parser.add_argument('-c', '--caption', action='store_true',
                        help='Add this flag to download caption when downloading photos')
    parser.add_argument('-l', '--headless', action='store_true',
                        help='If set, will use PhantomJS driver to run script as headless')
    parser.add_argument('-a', '--authentication', type=str, default=None,
                        help='path to authentication json file')
    parser.add_argument('-f', '--firefox_path', type=str, default=None,
                        help='path to Firefox installation')
    args = parser.parse_args()
    #  End Argparse #

    crawler = InstagramCrawler(headless=args.headless, firefox_path=args.firefox_path)
    crawler.crawl(dir_prefix=args.dir_prefix,
                  query=args.query,
                  crawl_type=args.crawl_type,
                  number=args.number,
                  caption=args.caption,
                  authentication=args.authentication)


if __name__ == "__main__":
    main()
