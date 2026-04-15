import eBayReportUploadGenerator

if __name__ == '__main__':
    continue_choice = "Y"

    while continue_choice == "Y" or continue_choice == "y":
        csvGenerator = eBayReportUploadGenerator.eBayReportUploadGenerator()
        csvGenerator.get_image_commandline()
        csvGenerator.upload_photo()
        csvGenerator.box_number = csvGenerator.get_card_box()
        csvGenerator.print_configuration()
        csvGenerator.create_files()
        print("")
        continue_choice = input("Would you like to do another set (Y/N)? ")
