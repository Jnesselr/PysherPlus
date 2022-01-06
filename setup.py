from setuptools import setup

VERSION = "2.0.1"


def readme():
    with open('README.md', encoding="utf8") as f:
        return f.read()


setup(
    name="PysherPlus",
    version=VERSION,
    description="Pusher websocket client for python, based on deepbrook's fork of Erik Kulyk's PythonPusherClient",
    long_description=readme(),
    long_description_content_type='text/markdown',
    keywords="pusher websocket client",
    author="Justin Nesselrotte",
    author_email="admin@jnesselr.org",
    license="MIT",
    url="https://github.com/jnesselr/PysherPlus",
    install_requires=[
        "websocket-client",
        "requests"
    ],
    packages=["pysherplus"],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Topic :: Internet',
        'Topic :: Software Development :: Libraries ',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ]
)
