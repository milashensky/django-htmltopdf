django-htmltopdf
==================

Bases on `incuna/django-wkhtmltopdf <https://github.com/incuna/django-wkhtmltopdf>`, but uses `arachnysdocker/athenapdf instead of wkhtmltopdf.

Converts HTML to PDF
--------------------

Provides Django views to wrap the HTML to PDF conversion. Based on `arachnys/athenapdf <https://github.com/arachnys/athenapdf>`.


Requirements
------------

Requires an docker, docker-py and and it also recommended to pull image of `arachnysdocker/athenapdf`


`docker pull arachnysdocker/athenapdf`


Python 2.6+ and 3.3+ are supported.
