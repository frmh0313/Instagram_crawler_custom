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
import gc
import resource

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
        firefox_binary = FirefoxBinary(firefox_path)
        options = webdriver.FirefoxOptions()

        if headless:
            options.set_headless(headless=True)
            options.set_preference("general.useragent.override", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.84 Safari/537.36")
            options.add_argument("lang=ko_KR")
            options.add_argument('window-size=1920x1080)')
        driver = webdriver.Firefox(firefox_binary=firefox_binary, firefox_options=options)
        self._driver = driver
        self._driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: function() { return [1, 2, 3, 4, 5];},});")
        self._driver.execute_script("Object.defineProperty(navigator, 'languages', {get: function() { return ['ko-KR', 'ko']}})")
        driver.implicitly_wait(10)

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
            num_of_posts = int(str(self._driver.find_element_by_xpath("//span[@class='_fd86t']").text).replace(',', ''))

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

    def scroll_to_num_of_posts(self, number):
        num_of_posts = int((self._driver.find_element_by_xpath("//span[@class='_fd86t']").text).replace(',', ''))
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

    # TODO: Ideas
    """
    1. Using multiple webdrivers in a row.
    2. Using AWS? / or Using headless mode in NIMS server
    3. Not using selenium. Using requests instead?
    4. Writing shell script - executing this crawler for every 3000 comments. Save the url of last post, and keep going another process from the post
    - Saving the url in outer file and load this file in the next process?
    5. Writing what crawled to the output file directly, without saving in memory. 
    """
    def click_and_scrape_captions(self, number, query, dir_prefix):
        #import tracemalloc
        #import multiprocessing
        print("Scraping captions...")
        # time1 = tracemalloc.take_snapshot()
        num_captions_in_file = 1000
        increment_wait = 0.05

        dir_name = query.lstrip(
            '#') + '.hashtag' if query.startswith('#') else query

        dir_path = os.path.join(dir_prefix, dir_name)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

        for post_num in range(number):
            # memory()
            # print('Memory usage:           : % 2.2f MB' % round(
            #     resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1)
            #       )
            captions = []
            sys.stdout.write("\033[F")
            print("\n0:Scraping captions {} / {}\n".format(post_num+1,number))
            if post_num == 0:  # Click on the first post
                self._driver.find_element_by_xpath(
                    FIREFOX_FIRST_POST_PATH
                ).click()
                self._driver.find_element_by_xpath(
                    FIREFOX_FIRST_POST_PATH).click()

                if number != 1:  #
                    trying_1 = True
                    wait_1 = 0
                    while trying_1:
                        try:
                            WebDriverWait(self._driver, wait_1).until(
                                EC.presence_of_element_located(
                                    (By.CSS_SELECTOR, CSS_RIGHT_ARROW)
                                )
                            )
                        except TimeoutException:
                            print("1:Timeout. No right arrow")
                            wait_1 += increment_wait
                            continue
                        except NoSuchElementException:
                            print("No right arrow")
                        else:
                            trying_1 = False
                            wait_1 = 0

            elif number != 1:  # Click Right Arrow to move to next post
                trying_2 = True
                wait_2 = 0
                while trying_2:
                    try:
                        url_before = self._driver.current_url
                        self._driver.find_element_by_css_selector(
                            CSS_RIGHT_ARROW).click()
                        WebDriverWait(self._driver, wait_2).until(
                            url_change(url_before))
                    except TimeoutException:
                        print("2:Time out in caption scraping at number {}. Trying again.\n".format(post_num+1))
                        wait_2 += increment_wait
                        continue
                    except NoSuchElementException as e:
                        print(e)
                        print("2:NoSuchElementException in {}. Trying again.\n".format(post_num+1))
                        break
                    else:
                        trying_2 = False
                        wait_2 = 0


            # Parse caption
            # + Parse date
            trying_parse = True
            wait_parse = 0
            while trying_parse:
                try:
                    time_element = WebDriverWait(self._driver, wait_parse).until(
                        EC.presence_of_element_located((By.TAG_NAME, "time"))
                    )
                    datetime = time_element.get_attribute('datetime')
                    date_title = time_element.get_attribute('title')
                    caption = time_element.find_element_by_xpath(
                        TIME_TO_CAPTION_PATH).text
                    caption_with_date = { 'count': post_num+1, 'caption':caption, 'datetime': datetime, 'datetime_title':date_title }
                    # caption = {}
                    # caption['text'] = time_element.find_element_by_xpath(
                    #     TIME_TO_CAPTION_PATH).text
                    # caption['datetime'] = datetime
                    # caption['datetime_title'] = date_title
                except TimeoutException:
                    print("PARSE: Time exception in {}. Trying again.\n".format(post_num+1))
                    wait_parse += increment_wait
                except NoSuchElementException:  # Forbidden
                    print("PARSE: Caption not found in the {} photo. Skip this post.\n".format(post_num+1))
                    caption = ""
                    break
                except StaleElementReferenceException:
                    print("PARSE: StaleElementReferenceException in {}. Trying to refresh".format(post_num+1))
                    wait_stale = 0
                    trying_stale = True
                    while trying_stale:
                        try:
                            url_before = self._driver.current_url
                            self._driver.find_element_by_css_selector(
                                CSS_RIGHT_ARROW).click()
                            WebDriverWait(self._driver, wait_stale).until(
                                url_change(url_before))
                        except TimeoutException:
                            print("PARSE:STALE:Trying again.\n")
                            #wait += 0.1
                            wait_stale += increment_wait
                            continue
                        else:
                            trying_stale = False
                            wait_stale = 0
                else:
                    trying_parse = False
                    wait_parse = 0


                count = post_num + 1
                filenumber = int(count / 1000) * 1000
                filename = str(filenumber) + '.txt'
                filepath = os.path.join(dir_path, filename)
                with codecs.open(filepath, 'a', encoding='utf8') as fout:
                    json_object = json.dumps(caption_with_date, ensure_ascii=False, indent=4)
                    json.dump(json_object, fout, ensure_ascii=False)


            # captions.append(caption_with_date)
            # self.data['captions'].extend(captions)
            # count = post_num + 1
            # if count % num_captions_in_file == 0:
            #     filename = str(count) +'.txt'
            #     filepath = os.path.join(dir_path, filename)
            #     print('file {}'.format(filename), 'writing')
            #
            #     caption_result = []
            #     for caption in self.data['captions']:
            #         caption_result.append({'count': caption['count'],
            #                                'caption': caption['caption'],
            #                                'datetime': caption['datetime'],
            #                                'datetime_title': caption['datetime_title']})
            #         json_object = json.dumps(caption_result, ensure_ascii=False, indent=4)
            #         with codecs.open(filepath, 'w', encoding='utf8') as fout:
            #             json.dump(json_object, fout, ensure_ascii=False)
            #
            # if count == number:
            #     filename = str(count) + '.txt'
            #     filepath = os.path.join(dir_path, filename)
            #     print('file {}'.format(filename), 'writing')
            #
            #     caption_result = []
            #     for caption in self.data['captions']:
            #         caption_result.append({'count': caption['count'],
            #                                'caption': caption['caption'],
            #                                'datetime': caption['datetime'],
            #                                'datetime_title': caption['datetime_title']})
            #         json_object = json.dumps(caption_result, ensure_ascii=False, indent=4)
            #         with codecs.open(filepath, 'w', encoding='utf8') as fout:
            #             json.dump(json_object, fout, ensure_ascii=False)
            # captions.append(datetime)
            # captions.append(date_title)

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
    # tracemalloc.start(5)
    main()
