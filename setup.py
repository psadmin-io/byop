from setuptools import setup #, find_packages
from pathlib import Path

HERE = Path(__file__).parent
README = (HERE / "README.md").read_text()
HISTORY = (HERE / "HISTORY.md").read_text()

setup_args = dict(
    name='byop',
    version='0.1.0',
    description='psadmin.io - Bring Your Own Patches IDPK Builder',
    long_description_content_type="text/markdown",
    long_description=README + '\n\n' + HISTORY,
    url='https://github.com/psadmin-io/io-byop',
    
    author='psadmin.io',
    author_email='info@psadmin.io',
    license='MIT',
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
    ],
    # packages=find_packages(''),
    keywords=['PeopleSoft', 'PeopleTools', 'CPU', 'Security Patches', 'Infrastructure DPK', 'IDPK'],
    include_package_data=True,
    py_modules=['byop'],
    install_requires=["click","requests","pyyaml"],
    entry_points={
        "console_scripts": [
            "byop=byop:cli",
        ]
    }
)

if __name__ == '__main__':
    setup(**setup_args)
