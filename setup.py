from setuptools import find_packages, setup

setup(
    name="employee_lending",
    version="1.6.0",
    description="Employee lending and repayment automation for ERPNext",
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
)
