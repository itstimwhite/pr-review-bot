from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="pr-review-bot",
    version="1.0.0",
    description="AI-powered PR review bot — research-backed code review using free models",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Tim White",
    author_email="tim@timwhite.co",
    url="https://github.com/itsTimWhite/pr-review-bot",
    license="MIT",
    packages=find_packages(),
    package_dir={"": "src"},
    python_requires=">=3.10",
    install_requires=[
        "requests>=2.28.0",
    ],
    entry_points={
        "console_scripts": [
            "pr-review-bot=pr_review_bot.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Quality Assurance",
    ],
)
