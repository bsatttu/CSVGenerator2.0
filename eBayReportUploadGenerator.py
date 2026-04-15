# CSV Generator for eBay variation listings
# Future Improvements
#  - Handle sets over 250 cards without numbers
#  - Run as a web service
#  - Allow arguments to be passed in
#  - Read in box and short_name from config file

import pandas
import re
import sys
import os
import math
import requests
import gspread
from scp import SCPClient
import paramiko
from generatorConfig import GeneratorConfig, GeneratorConfigException
import json

class eBayReportUploadGenerator:

    def __init__(self, init_file='defaults.ini'):
        # Get config
        self.config = {}
        try:
            self.config = GeneratorConfig(init_file)
        except GeneratorConfigException as e:
            print(e)
            sys.exit()

        self.sport_mapping = {
            "Baseball": "BB",
            "Basketball": "BK",
            "Football": "FB",
            "Hockey": "HK"
        }
        self.box_number = ""
        self.number_of_rows = 0
        self.number_of_rows_per_file = 0
        self.card_set = ""
        self.card_year = ""
        self.sport_long = ""
        self.sport_short = ""
        self.card_set_short = ""
        self.photoURLComplete = ""
        self.storeCategory = ""

        # Variables from config file
        self.working_directory = self.config['DEFAULT']['working_directory']
        self.template_filename = self.config['DEFAULT']['templateFileName']
        self.input_filename = self.config['inputData']['inputFileName']
        self.photoURLBeginning = self.config['DEFAULT']['photoURLBeginning']
        self.local_jpg_location = self.config['DEFAULT']['local_jpg_location']

        self.ssh_host = self.config['ssh']['ssh_host']
        self.ssh_username = self.config['ssh']['ssh_username']
        self.ssh_password = ""
        self.ssh_remote_file_path = self.config['ssh']['ssh_remote_file_path']

        self.input_file_headers = {
            'description': self.config['inputData']['inputHeader_description'],
            'price': self.config['inputData']['inputHeader_price'],
            'count': self.config['inputData']['inputHeader_count'],
            'serial_number': self.config['inputData']['inputHeader_serial_number']
        }
        self.default_price = self.config['inputData']['default_price']
        # If use_zero_qty is false, it will only list the cards with a nonzero qty in the output file
        # If the count field is not there, it will use everything
        self.include_zero_count = self.config['inputData']['use_zero_qty'].lower() == 'true'
        self.sport_long = self.config['set_values']['sport']

        # Set up Pandas dataframes
        self.outputDF = pandas.DataFrame()
        self.inputDF = pandas.DataFrame()
        self.initialize_template(self.working_directory + self.template_filename)
        self.initialize_input(self.working_directory + self.input_filename)

    def upload_photo_commandline(self):
        # Check if the local photo exists or if it is already there
        self.photoURLComplete = self.photoURLBeginning + self.card_set_short + ".jpg"
        if self.verify_photo_at_url(self.photoURLComplete):
            print("Photo already exists at " + self.photoURLComplete)
            print("Will not upload a new one")
        elif self.verify_local_photo(self.full_local_jpg_location):
            if self.ssh_password == "":
                self.ssh_password = input("Uploading new file.  Password:")

            if self.upload_file(self.ssh_host, self.ssh_remote_file_path + self.card_set_short + ".jpg",
                                self.ssh_username, self.ssh_password,
                                self.full_local_jpg_location):
                print("Photo uploaded successfully: " + self.ssh_remote_file_path + self.card_set_short + ".jpg")

            if not self.verify_photo_at_url(self.photoURLComplete):
                print("Photo did not upload successfully, please retry")
        else:
            print("CAUTION!!!! No photo exists for this set short name: " + self.card_set_short)

    def create_files(self):
        # Set values in top row
        self.outputDF.loc[0, 'StoreCategory'] = self.storeCategory
        self.outputDF.loc[0, 'PicURL'] = self.photoURLBeginning + self.card_set_short + ".jpg"
        self.outputDF.loc[0, 'C:Set'] = self.card_set
        self.outputDF.loc[0, 'C:Year'] = self.card_year
        self.outputDF.loc[0, 'C:Sport'] = self.sport_long

        # Add individual cards as variations
        self.outputDF.loc[0, 'Relationship'] = ""
        self.outputDF.loc[0, 'Quantity'] = ""
        self.outputDF.loc[0, 'StartPrice'] = ""

        if self.include_zero_count or self.input_file_headers['count'] not in self.inputDF.columns:
            self.number_of_rows = len(self.inputDF.index)
        else:
            self.number_of_rows = (self.inputDF[self.input_file_headers['count']] != 0).sum()
            self.inputDF = self.inputDF[self.inputDF[self.input_file_headers['count']] != 0].reset_index(drop=True)
        self.number_of_rows_per_file = 250

        # Determine number of rows per file
        # Over 5000 lines, we won't worry about it and just go with 250 rows per file
        if self.number_of_rows <= 250:
            self.number_of_rows_per_file = self.number_of_rows
        elif self.number_of_rows <= 800:
            while (self.number_of_rows % self.number_of_rows_per_file < 100 and
                   self.number_of_rows % self.number_of_rows_per_file != 0):
                self.number_of_rows_per_file -= 50
        elif self.number_of_rows <= 5000:
            while (self.number_of_rows % self.number_of_rows_per_file < 50 and
                   self.number_of_rows % self.number_of_rows_per_file != 0):
                self.number_of_rows_per_file -= 10

        # Create Files
        output_filename = ""
        relationship_details = "Number="
        outputDF_copy = self.outputDF.copy(deep=True)
        for index in self.inputDF.index:
            if index % self.number_of_rows_per_file == 0:
                # This is the first row for the file, so set up file
                self.outputDF = outputDF_copy.copy(deep=True)
                relationship_details = "Number="
                first_card_number = re.search(r'#(\S+)',
                                              self.inputDF[self.input_file_headers['description']][index]).group(1)
                last_card_number = ""
                if self.number_of_rows_per_file < self.number_of_rows:
                    if index + self.number_of_rows_per_file < self.number_of_rows:
                        last_card_number = re.search(r'#(\S+)', self.inputDF[self.input_file_headers['description']]
                                                        [index + self.number_of_rows_per_file - 1]).group(1)
                    else:
                        last_card_number = re.search(r'#(\S+)', self.inputDF[self.input_file_headers['description']]
                                                        [self.number_of_rows - 1]).group(1)
                    output_filename = self.working_directory + self.card_set_short + \
                                           first_card_number + "-" + last_card_number + ".csv"
                    self.outputDF.loc[0, 'Title'] = self.get_list_title(self.card_set, self.sport_short,
                                                                        first_card_number, last_card_number,
                                                                        self.box_number)
                else:
                    self.outputDF.loc[0, 'Title'] = self.get_list_title(self.card_set, self.sport_short, "0", "0",
                                                                        self.box_number)
                    output_filename = self.working_directory + self.card_set_short + ".csv"

            card_number = re.search(r'#(.*?)$', self.inputDF[self.input_file_headers['description']][index]).group(1)

            # Add the serial number to the description if it exists
            if not math.isnan(self.inputDF[self.input_file_headers['serial_number']][index]):
                card_number += " /" + str(int(self.inputDF[self.input_file_headers['serial_number']][index]))

            if len(card_number) > 65:
                # The Relationship line can only be 65 characters long
                print(card_number + " is too long, please fix and run again")
                return False

            # Print the details for each line
            self.outputDF.loc[index + 1, 'RelationshipDetails'] = "Number=" + card_number
            self.outputDF.loc[index + 1, 'Relationship'] = "Variation"
            if self.input_file_headers['price'] in self.inputDF.keys():
                price = re.sub(r"\$", "", str(self.inputDF[self.input_file_headers['price']][index]))
            else:
                price = self.default_price
            self.outputDF.loc[index + 1, 'StartPrice'] = price

            if self.input_file_headers['count'] in self.inputDF.keys():
                self.outputDF.loc[index + 1, 'Quantity'] = self.inputDF[self.input_file_headers['count']][index]
            else:
                self.outputDF.loc[index + 1, 'Quantity'] = "0"

            if index % self.number_of_rows_per_file == 0:
                # if this is the first line of the file, then we just add the card number to the Relationship field
                relationship_details = relationship_details + card_number
            else:
                # if this is not the first line of the file, add a semicolon and card number to the Relationship field
                relationship_details = relationship_details + ";" + card_number

            if (index + 1) % self.number_of_rows_per_file == 0 or (index + 1) == self.number_of_rows:
                # This is the last row for the file, so we need to print it out
                self.outputDF.loc[0, 'RelationshipDetails'] = relationship_details
                self.write_csv(self.outputDF, output_filename, False)

        self.outputDF = outputDF_copy.copy(deep=True)
        return True

    def get_csv(self, filename):
        try:
            df = pandas.read_csv(filename)
        except Exception as template_exception:
            print('Pandas exception occurred on template: {}'.format(template_exception))
            sys.exit()
        return df

    def write_csv(self, df, filename, index_option):
        try:
            df.to_csv(filename, index=index_option)
        except Exception as template_exception:
            print('Pandas exception occurred on template: {}'.format(template_exception))
            sys.exit()
        print("Created " + filename)
        return True

    def get_set(self, card):
        cardset = re.search(r'^(.*?) #', card).group(1)
        return cardset

    def get_set_year(self, cardset):
        setyear = re.search(r"^\d\d\d\d", cardset).group()
        return setyear

    def get_sport(self):
        sport = ""
        sport_list = {
            "1": "Baseball",
            "2": "Basketball",
            "3": "Football",
            "4": "Hockey"
        }
        if 'sport' in self.config['set_values'].keys():
            if self.config['set_values']['sport'] in sport_list.values():
                return self.config['set_values']['sport']
        else:
            sport = "0"
            while sport not in sport_list:
                for sport_index in sport_list:
                    print(sport_index + " " + sport_list[sport_index])
                sport = input("Which sport is this?")

        return sport_list[sport]

    def get_sport_short(self, sport):
        if sport not in self.sport_mapping:
            print("Sport does not exist: " + sport)
            return False

        return self.sport_mapping[sport]

    def get_card_box(self):
        return input("What box should these cards go in? ")

    def get_store_category(self, sport, year):
        # If a config file exists for the store categories, read it in
        categories_file = ""
        if 'categories_file' in self.config['DEFAULT']:
            categories_file = self.working_directory + self.config['DEFAULT']['categories_file']

        if categories_file and os.path.exists(categories_file):
            with open(categories_file, 'r') as categories_filehandle:
                store_categories = json.load(categories_filehandle)
        else:
            store_categories = {
                "BB": {
                    "195": "38799025018",
                    "196": "38799026018",
                    "197": "38799027018",
                    "198": "38799028018",
                    "199": "38799029018",
                    "200": "38799030018",
                    "201": "38799031018",
                    "202": "38799032018"
                },
                "BK": {
                    "195": "",
                    "196": "",
                    "197": "33722080018",
                    "198": "43107002018",
                    "199": "",
                    "200": "",
                    "201": "",
                    "202": ""
                },
                "FB": {
                    "195": "34283446018",
                    "196": "",
                    "197": "",
                    "198": "34283446018",
                    "199": "",
                    "200": "",
                    "201": "",
                    "202": ""
                }
            }

        year = re.search(r"^\d\d\d", year).group()

        if store_categories[sport][year] == "":
            print('Warning!!! There is no category for {} {}'.format(year, sport))

        return store_categories[sport][year]

    def get_image_commandline(self):
        image_list = {}
        counter = 1
        print(self.card_set)
        print("What is the image that goes with this set?")
        if os.path.exists(self.local_jpg_location):
            dir_list = os.listdir(self.local_jpg_location)
            for file in dir_list:
                if file.endswith(".jpg"):
                    image_list[str(counter)] = os.path.splitext(file)[0]
                    print("{}: {}".format(counter, image_list[str(counter)]))
                    counter += 1
        print("O: Other")
        selection = input("? ")
        if selection in image_list.keys():
            self.card_set_short = image_list[selection]
            self.full_local_jpg_location = os.path.join(self.local_jpg_location, self.card_set_short + ".jpg")
        else:
            self.card_set_short = input("What is the short name for this set?")
        return True

    def set_image(self, full_jpg_path):
        self.full_local_jpg_location = full_jpg_path
        self.local_jpg_location = os.path.dirname(os.path.abspath(full_jpg_path))
        self.card_set_short = os.path.basename(full_jpg_path).split('.')[0]

    def verify_local_photo(self, full_file_path):
        if os.path.exists(full_file_path):
            return True
        else:
            return False

    def get_list_title(self, set_name, sport_short_name, first_number, last_number, card_box):
        # Create the listing title.  The listing title can be at more 80 characters
        # put 0 in the first number if it does not need the numbers in the title
        # all arguments must be strings

        if first_number == "0":
            list_title = set_name + " " + sport_short_name + " - You Pick - Complete Your Set (" + card_box + ")"
        else:
            list_title = set_name + " " + sport_short_name + " #" + first_number + "-" + last_number + \
                         " - You Pick - Complete Your Set (" + card_box + ")"

        if len(list_title) > 80:
            # Second try to get a title that is not too long
            if first_number == "0":
                list_title = set_name + " " + sport_short_name + " - You Pick - (" + card_box + ")"
            else:
                list_title = set_name + " " + sport_short_name + " #" + first_number + "-" + last_number + \
                             " - You Pick (" + card_box + ")"

        if len(list_title) > 80:
            # Third try to get a title that is not too long
            if first_number == "0":
                list_title = set_name + " " + sport_short_name + " You Pick (" + card_box + ")"
            else:
                list_title = set_name + " " + sport_short_name + " #" + first_number + "-" + last_number + \
                             " You Pick (" + card_box + ")"

        if len(list_title) > 80:
            # Give up.  It will have to be manually shortened
            print("CAUTION!!!!  Title is too long and will need to be fixed: " + list_title)

        return list_title

    def verify_photo_at_url(self, path):
        r = requests.head(path)
        return r.status_code == requests.codes.ok

    def upload_file(self, host_name, remote_file_path, username, password, local_file_path):
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh_client.connect(host_name, 22, username, password)
            scp = SCPClient(ssh_client.get_transport())
            scp.put(local_file_path, remote_file_path)
        except paramiko.AuthenticationException as error:
            print('File not uploaded: {}'.format(error))
            return False
        except paramiko.ssh_exception as error:
            print('File not uploaded: {}'.format(error))
            return False

        return True

    def print_configuration(self):
        print("Card Set: " + self.card_set)
        print("Local photo: " + self.full_local_jpg_location)
        print("Box: " + self.box_number)
        print("Sport: " + self.sport_long)

    def initialize_template(self, template_file):
        if not os.path.isfile(template_file):
            print('File not found: {}'.format(template_file))
            return False

        # Read in file
        self.outputDF = self.outputDF.iloc[0:0]
        # Read template file into a Pandas dataframe
        self.outputDF = self.get_csv(template_file)

        # Need to make sure some fields are a strings instead of ints
        self.outputDF[['C:Year']] = self.outputDF[['C:Year']].astype(str)
        self.outputDF[['Relationship']] = self.outputDF[['Relationship']].astype(str)
        self.outputDF[['Quantity']] = self.outputDF[['Quantity']].astype(str)
        self.outputDF[['StartPrice']] = self.outputDF[['StartPrice']].astype(str)
        self.outputDF[['StoreCategory']] = self.outputDF[['StoreCategory']].astype(str)
        return True

    def initialize_input(self, input_file):
        if not os.path.isfile(input_file):
            print('File not found: {}'.format(input_file))
            return False

        # Read in file
        self.inputDF = self.inputDF.iloc[0:0]
        # Load the input csv file into a pandas dataframe
        self.inputDF = self.get_csv(input_file)
        # Drop empty rows
        self.inputDF.dropna(axis=0, how='all', inplace=True)
        self.card_set = self.get_set(self.inputDF.loc[0][self.input_file_headers['description']])
        self.card_year = self.get_set_year(self.card_set)

        return True

    def open_boxes_spreadsheet(self):
        # Authenticate with the json token
        json_token = self.working_directory + 'inventory-box-tracker-7d7f45f6389b.json'
        sheets_client = gspread.service_account(filename=json_token)

        # Open the spreadsheet and select the worksheet
        box_sheet = sheets_client.open("savageb12")
        box_worksheet = box_sheet.worksheet('Box Status')

        # Read data from the sheet (example: get all values)
        data = box_worksheet.get_all_values()

        # Print the data
        for row in data:
            print(row)


if __name__ == '__main__':
    continue_choice = "Y"

    while continue_choice == "Y" or continue_choice == "y":
        csvGenerator = eBayReportUploadGenerator()
        csvGenerator.open_boxes_spreadsheet()

        # Set up derived variables
        csvGenerator.sport_long = csvGenerator.get_sport()
        csvGenerator.sport_short = csvGenerator.get_sport_short(csvGenerator.sport_long)
        csvGenerator.storeCategory = csvGenerator.get_store_category(csvGenerator.sport_short, csvGenerator.card_year)

        csvGenerator.get_image_commandline()
        csvGenerator.upload_photo_commandline()
        csvGenerator.box_number = csvGenerator.get_card_box()
        csvGenerator.print_configuration()
        csvGenerator.create_files()
        print("")
        continue_choice = input("Would you like to do another set (Y/N)? ")
