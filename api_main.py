#!/home/djackson/PycharmProjects/PlayonAPI/.venv/bin/python3

import os
import json
import re
from pathlib import Path
from time import sleep

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# Load configuration
def load_config():
    config_path = Path(__file__).parent / 'config.json'
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        # Format the base_url with IP and port
        config['server']['base_url'] = config['server']['base_url'].format(
            ip=config['server']['ip'],
            port=config['server']['port']
        )
        return config
    except FileNotFoundError:
        print(f"Error: Configuration file not found at {config_path}")
        raise
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in configuration file {config_path}")
        raise
    except KeyError as e:
        print(f"Error: Missing required configuration key: {e}")
        raise

# Load configuration
config = load_config()
non_provider_links = config.get('non_provider_links', [])
base_url = config['server']['base_url']

def setup_webdriver():
    """
    Set up and return a configured Chrome webdriver using settings from config
    """
    chrome_options = Options()
    if config['webdriver'].get('headless', False):
        chrome_options.add_argument("--headless")

    # Add any additional options from config
    for arg in config['webdriver'].get('chrome_options', []):
        chrome_options.add_argument(arg)

    # Setup the webdriver with ChromeDriverManager to automatically manage driver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    return driver


def provider_check():
    url = f"{base_url}/"
    """
    Connect to a web page and parse out its entries

    :param url: The URL of the webpage to scrape
    :return: List of parsed entries
    """
    # Setup the webdriver
    driver = setup_webdriver()

    try:
        # Navigate to the webpage
        driver.get(url)

        # Wait for page to load (you might want to use explicit waits in a real-world scenario)
        wait = WebDriverWait(driver, 10)
        links = WebDriverWait(driver, 20).until(EC.visibility_of_all_elements_located((By.CSS_SELECTOR, "div#first_page.page")))

        # Find and click the 'All' link by its image path
        all_link = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//img[@src='/images/categories/all.png']"))
        )
        all_link.click()

        # Get the page source
        page_source = driver.page_source


        # Use BeautifulSoup for parsing
        soup = BeautifulSoup(page_source, 'html.parser')

        # Example of finding entries (modify selector as needed)
        # This is a generic example - you'll need to inspect the specific website's HTML structure
        entries = soup.find_all('img', href_='/data/data.xml\?id=')

        # Extract text from entries
        parsed_entries = [entry['src'] for entry in entries]
        providers = []
        for ea_parsed_entry  in parsed_entries:
            matcher = re.match(r'.+id=([^&]+)', ea_parsed_entry)
            if matcher:
                provider = matcher.group(1)
                if provider not in non_provider_links:
                    providers.append(provider)
        print(f"Found {len(providers)} providers")
        print(f"Providers: {providers}")


        return providers

    except Exception as e:
        print(f"An error occurred: {e}")
        return []

    finally:
        # Always close the driver
        #sleep(120)
        driver.quit()

def search_all_providers(searchterm):
    providers = provider_check()
    """
    Connect to a web page and parse out its entries

    :param url: The URL of the webpage to scrape
    :return: List of parsed entries
    """
    found_results = {}
    # Setup the webdriver
    driver = setup_webdriver()

    try:
        # Navigate to the webpage
        driver.get(url)

        # Wait for page to load (you might want to use explicit waits in a real-world scenario)
        wait = WebDriverWait(driver, 10)
        links = WebDriverWait(driver, 20).until(EC.visibility_of_all_elements_located((By.CSS_SELECTOR, "div#first_page.page")))

        # Find and click the 'All' link by its image path
        all_link = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//img[@src='/images/categories/all.png']"))
        )
        all_link.click()

        # Get the page source
        #page_source = driver.page_source


        # Use BeautifulSoup for parsing
        #soup = BeautifulSoup(page_source, 'html.parser')

        # Example of finding entries (modify selector as needed)
        # This is a generic example - you'll need to inspect the specific website's HTML structure
        #entries = soup.find_all('img', class_='provider_square')

        for provider in providers:
            try:
                print(f"Searching for {provider}")
                provider_link = wait.until(
                    EC.element_to_be_clickable((By.XPATH, f"//img[@src='/images/provider.png?id={provider}&rsm=pz&width=128&height=128&rst=16']"))
                )
                #driver.get(f"{url}/#{provider}")
                provider_link.click()
                print(f"loaded {provider}")
                search_field = wait.until(EC.element_to_be_clickable((By.NAME, "searchterm")))

                #search_field = driver.find_element(By.NAME, "searchterm")
                search_field.send_keys(searchterm)
                search_field.send_keys(Keys.ENTER)
                #print(f"found {search_field}")
                xpath_expression = f"//span[contains(text(), '{searchterm}')]"

                # Find all matching span elements
                span_elements = driver.find_elements(By.XPATH, xpath_expression)
                print("Found span elements")

                # Iterate through the found elements and print their text (optional)
                if span_elements:
                    for span in span_elements:
                        if provider not in found_results:
                            found_results[provider] = []
                        found_results[provider].append(span.text)
                        print(f"Found title {span.text}")
                try:
                    # Find and click the 'All' link by its image path
                    print(f"waiting to click back")
                    back_link = wait.until(
                        EC.element_to_be_clickable((By.XPATH, "//span[@id='back_arrow_first']"))
                    )
                    back_link.click()
                    print(f"clicked back")
                except Exception as e:
                    print(f"An error occurred: {e}")

            except Exception as e:
                print(f"An error occurred: {e}")

    except Exception as e:
        print(f"An error occurred: {e}")
        return []

    finally:
        # Always close the driver
        #sleep(120)
        driver.quit()

def main():
    import sys
    # Example usage
    entries = search_all_providers(' '.join(sys.argv[1:]))

    # Print out the entries
    for entry in entries:
        print(json.dumps(entry))


if __name__ == "__main__":
    main()
