import setuptools
setuptools.setup(
    # Includes all other files that are within your project folder 
    include_package_data=True,
  
    # Name of your Package
    name='custom-modules',
 
    # Project Version
    version='1.0',
     
    # Website for your Project or Github repo
    url="https://github.com/CherMet90/custom_python_modules",
 
    # Projects you want to include in your Package
    packages=setuptools.find_packages (),
    
    # Dependencies/Other modules required for your package to work
    install_requires=['pynetbox', 'colorama', 'paramiko', 'prettytable'],
 
)