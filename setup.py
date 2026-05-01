from setuptools import find_packages, setup


setup(
    name="downify",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    package_data={"downify": ["static/*"]},
    install_requires=[
        "fastapi>=0.115.0",
        "httpx>=0.27.0",
        "python-dotenv>=1.0.1",
        "uvicorn[standard]>=0.30.0",
    ],
    entry_points={"console_scripts": ["downify-web=downify.web:main"]},
    python_requires=">=3.10",
)
