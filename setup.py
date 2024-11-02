from setuptools import setup, find_packages

setup(
    name="kubewhisper",
    version="1.0.5",
    packages=find_packages(),
    install_requires=[
        "requests",
    ],
    entry_points={
        'console_scripts': [
            'kubewhisper=cli.main:main',
        ],
    },
    author="Branko Petric",
    author_email="bane@brankopetric.com",
    description="KubeWhisper - Generate kubectl commands from natural language queries",
    long_description=open('README.md').read(),
    long_description_content_type="text/markdown",
    url="https://github.com/petricbranko/kubewhisper",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.9',
)