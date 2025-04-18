from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = fh.read().splitlines()

setup(
    name="website-extractor",
    version="1.0.0",
    author="CloneX",
    author_email="your.email@example.com",  # Replace with your actual email
    description="A tool to extract and archive entire websites with advanced rendering capabilities",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/sirioberati/website-extractor",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Utilities",
    ],
    python_requires=">=3.7",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "website-extractor=app:main",
        ],
    },
    include_package_data=True,
) 