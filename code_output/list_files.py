import os
import sys

def list_file_sizes(folder_path):
    """
    Lists all files in the specified folder and prints their sizes in bytes.
    """
    if not os.path.isdir(folder_path):
        print(f"Error: Directory not found at '{folder_path}'")
        return

    print(f"--- File Sizes in: {folder_path} ---")
    
    # Iterate over all entries in the directory
    for entry in os.listdir(folder_path):
        full_path = os.path.join(folder_path, entry)
        
        # Check if the entry is a file (and not a directory or symlink)
        if os.path.isfile(full_path):
            try:
                # Get the size of the file in bytes
                size = os.path.getsize(full_path)
                print(f"{entry}: {size} bytes")
            except OSError as e:
                # Handle potential permission or reading errors
                print(f"{entry}: Error reading size ({e})")

if __name__ == "__main__":
    # Determine the folder path to use
    if len(sys.argv) > 1:
        # Use the path provided as a command-line argument
        target_directory = sys.argv[1]
    else:
        # Default to the current working directory if no argument is given
        target_directory = "."
    
    list_file_sizes(target_directory)