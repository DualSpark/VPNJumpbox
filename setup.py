from setuptools import setup

setup(
    name="vpnjumpbox",
    version="0.1",
    install_requires=[
        'cfn-environment-base==0.8'
    ],
    dependency_links=[
        'https://github.com/DualSpark/cloudformation-environmentbase/zipball/0.8.0#egg=cfn-environment-base-0.8.0'
    ],
    package_dir={"": "src"},
    include_package_data=True,
    zip_safe=True
)
