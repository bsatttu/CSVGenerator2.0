import sys
import tkinter as tk
from tkinter import *
from tkinter import ttk
from tkinter import filedialog
from tkinter import messagebox
from tkinter import simpledialog
import eBayReportUploadGenerator


class eBayReportUploadGeneratorUI:

    def __init__(self):
        self.csvGenerator = eBayReportUploadGenerator.eBayReportUploadGenerator()

        self.main_window = tk.Tk()
        self.main_window.geometry("655x565")
        self.main_window.title('eBay Report Upload Generator')
        self.main_window.iconbitmap("ebay.ico")
        self.jpg_filename_with_path = ""
        self.template_filename_with_path = ""
        self.input_filename_with_path = ""

        self.set_name_value = tk.StringVar(self.main_window, self.csvGenerator.card_set)
        self.box_number_value = tk.StringVar(self.main_window)
        self.sport_value = tk.StringVar(self.main_window)

        self.menubar = tk.Menu(self.main_window)
        self.filemenu = tk.Menu(self.menubar, tearoff=0)
        self.filemenu.add_command(label="Load Template", command=self.load_template)
        self.filemenu.add_command(label="Load Input", command=self.load_input)
        self.filemenu.add_separator()
        self.filemenu.add_command(label="Exit", command=self.main_window.quit)
        self.menubar.add_cascade(label="File", menu=self.filemenu)
        self.main_window.config(menu=self.menubar)

        self.set_name_label = tk.Label(self.main_window, text="Set Name:")
        self.set_name_label.grid(row=0, column=0, sticky=E, padx=2, pady=2)
        self.set_name_entry = tk.Entry(self.main_window, textvariable=self.set_name_value, width=90)
        self.set_name_entry.grid(row=0, column=1, sticky=W, padx=2, pady=2)
        self.box_number_label = tk.Label(self.main_window, text="Box Number:")
        self.box_number_label.grid(row=1, column=0, sticky=E, padx=2, pady=2)
        self.box_number_entry = tk.Entry(self.main_window, textvariable=self.box_number_value, width=90)
        self.box_number_entry.grid(row=1, column=1, sticky=W, padx=2, pady=2)
        self.sport_label = tk.Label(self.main_window, text="Sport:")
        self.sport_label.grid(row=2, column=0, sticky=E, padx=2, pady=2)
        self.sport_combobox = ttk.Combobox(self.main_window, values=list(self.csvGenerator.sport_mapping.keys()),
                                           textvariable=self.sport_value, justify="left")
        self.sport_combobox.grid(row=2, column=1, sticky=W, padx=2, pady=2)
        self.sport_combobox.current(list(self.csvGenerator.sport_mapping.keys()).index(self.csvGenerator.sport_long))

        self.jpg_open_button = tk.Button(self.main_window, text="Select Image", command=self.open_jpg_dialog)
        self.jpg_open_button.grid(row=3, column=0, sticky=E, padx=2, pady=2)
        self.selected_jpg_file_label = tk.Label(self.main_window, text=" ")
        self.selected_jpg_file_label.grid(row=3, column=1, sticky=W, padx=2, pady=2)

        self.create_button = tk.Button(self.main_window, text="Create Files", command=self.press_create_files)
        self.create_button.grid(row=5, column=0, columnspan=2, pady=10)

        self.reset_button = tk.Button(self.main_window, text="Reset", command=self.reset_ui)
        self.reset_button.grid(row=4, column=0, padx=2, pady=2)

        self.statusbox = tk.Text(self.main_window)
        self.statusbox.grid(row=6, column=0, columnspan=2, padx=5, pady=2)
        sys.stdout.write = self.redirector

        self.main_window.mainloop()

    def redirector(self, input_str):
        #  Causes stdout to be written to the statusbox
        self.statusbox.insert("end", input_str)

    def open_jpg_dialog(self):
        file_path = self.csvGenerator.local_jpg_location
        image_file_dialog = filedialog.askopenfile(title="Select an image", filetypes=[("JPG Files", "*.jpg")],
                                                   initialdir=file_path)
        if image_file_dialog:
            self.selected_jpg_file_label.config(text=f"{image_file_dialog.name}")
            self.jpg_filename_with_path = f"{image_file_dialog.name}"

    def press_create_files(self):
        if self.set_name_value.get() == "" or self.box_number_value.get() == "" or self.jpg_filename_with_path == "":
            messagebox.showwarning("Warning", "Not all fields are filled in")
        else:
            self.csvGenerator.sport_long = self.sport_value.get()
            self.csvGenerator.card_set = self.set_name_value.get()
            self.csvGenerator.box_number = self.box_number_value.get()
            self.csvGenerator.card_year = self.csvGenerator.get_set_year(self.csvGenerator.card_set)
            self.csvGenerator.sport_short = self.csvGenerator.get_sport_short(self.csvGenerator.sport_long)
            self.csvGenerator.storeCategory = self.csvGenerator.get_store_category(self.csvGenerator.sport_short,
                                                                                   self.csvGenerator.card_year)
            self.csvGenerator.set_image(self.jpg_filename_with_path)
            self.upload_photo()
            self.csvGenerator.print_configuration()
            self.csvGenerator.create_files()

        return True

    def upload_photo(self):
        # Check if the local photo exists or if it is already there
        self.csvGenerator.photoURLComplete = (self.csvGenerator.photoURLBeginning + self.csvGenerator.card_set_short +
                                              ".jpg")
        if self.csvGenerator.verify_photo_at_url(self.csvGenerator.photoURLComplete):
            messagebox.showwarning("Warning", "Photo already exists at " + self.csvGenerator.photoURLComplete +
                                   "\nWill not upload a new one.")
        elif self.csvGenerator.verify_local_photo(self.csvGenerator.full_local_jpg_location):
            if self.csvGenerator.ssh_password == "":
                self.csvGenerator.ssh_password = simpledialog.askstring("Password", "Enter password:", show="*")
            if self.csvGenerator.upload_file(self.csvGenerator.ssh_host, self.csvGenerator.ssh_remote_file_path +
                                             self.csvGenerator.card_set_short + ".jpg",
                                             self.csvGenerator.ssh_username, self.csvGenerator.ssh_password,
                                             self.csvGenerator.full_local_jpg_location):
                print("Photo uploaded successfully: " + self.csvGenerator.ssh_remote_file_path +
                      self.csvGenerator.card_set_short + ".jpg")

            if not self.csvGenerator.verify_photo_at_url(self.csvGenerator.photoURLComplete):
                messagebox.showwarning("Warning", "Photo did not upload successfully")
        else:
            messagebox.showwarning("Warning", "CAUTION!!!! No photo exists for this set short name: " +
                                   self.csvGenerator.card_set_short)

    def load_template(self):
        file_path = self.csvGenerator.working_directory
        template_file_dialog = filedialog.askopenfile(title="Select a template", filetypes=[("CSV Files", "*.csv")],
                                                      initialdir=file_path)
        if template_file_dialog:
            self.template_filename_with_path = f"{template_file_dialog.name}"
            self.csvGenerator.initialize_template(self.template_filename_with_path)
        return True

    def load_input(self):
        file_path = self.csvGenerator.working_directory
        input_file_dialog = filedialog.askopenfile(title="Select an input file", filetypes=[("CSV Files", "*.csv")],
                                                   initialdir=file_path)
        if input_file_dialog:
            self.input_filename_with_path = f"{input_file_dialog.name}"
            self.csvGenerator.initialize_input(self.input_filename_with_path)
            self.set_name_entry.delete(0, "end")
            self.set_name_entry.insert(0, self.csvGenerator.card_set)
        return True

    def reset_ui(self):
        self.csvGenerator.initialize_input(self.csvGenerator.working_directory + self.csvGenerator.input_filename)
        self.set_name_entry.delete(0, "end")
        self.set_name_entry.insert(0, self.csvGenerator.card_set)
        self.box_number_entry.delete(0, "end")
        self.selected_jpg_file_label.config(text=" ")
        self.statusbox.delete('1.0', END)


if __name__ == '__main__':
    eBayReportUploadGeneratorUI()
