import csv

def print_csv_rows(file_name):
    try:
        with open(file_name, 'r') as file:
            csv_reader = csv.reader(file)
            for row in csv_reader:
                print(row)
    except FileNotFoundError:
        print("File not found. Please check the file name and path.")

print_csv_rows('example.csv')