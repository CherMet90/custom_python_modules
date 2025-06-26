import setuptools
setuptools.setup(
    # Includes all other files that are within your project folder 
    include_package_data=True,
  
    # Name of your Package
    name='custom-modules',
 
    # Project Version
    version='1.1.0',
     
    # Website for your Project or Github repo
    url="https://github.com/CherMet90/custom_python_modules",
 
    # Projects you want to include in your Package
    packages=setuptools.find_packages (),
    
    # Dependencies/Other modules required for your package to work
    install_requires=[
    'setuptools==68.2.2',
    'pynetbox==7.2.0',
    'colorama==0.4.6',
    'paramiko==3.3.1',
    'prettytable==3.9.0',
    'transliterate==1.10.2',
    'ratelimit==2.2.1',
    'backoff==2.2.1',
    ],
 
)