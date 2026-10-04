# Change Data Management Service Project at kSynerX

**Last modified:** 10.05.2026\
**Copyright:** (c) Linh Truong, all rights reserved

## Goal

The goal of this assignment is to develop a prototype of a simple
**Change Data Management Service (CDMS)** for storing only changes of
data, including:

-   Emulating a real inventory service (with limited features).
-   Developing a change data service with different update mechanisms.
-   Implementing exactly once change with possible failure handles.
-   Performing tests under spike loads.

## Basic System Specification

### Emulating Vietful Inventory Service

Based on the API described at:

https://ext.stg.vnfai.com/doc/index.html

### Database

-   PostgreSQL

### Change Data Management Service (CDMS)

The CDMS is a composite service supporting three data-processing
mechanisms:

1.  Querying data via pre-defined scheduled intervals.
2.  Receiving data via webhook callbacks.
3.  Receiving data via Excel files uploaded via REST API.

### Emulated Data

Use Faker:

https://faker.readthedocs.io/en/master/

### Data for Management

The focus is inventory product data:

https://ext.stg.vnfai.com/doc/index.html#tag/Products

The goal is to capture new data about products, for example:

-   New products.
-   Changes to existing products.

## Functionality Requirements

-   CDMS should run on a **single machine**.
-   **Exactly once update:** CDMS only stores new data into the
    database. No old data and no duplicated data are allowed.
-   CDMS should work correctly under failures of:
    -   CDMS itself.
    -   Vietful service.
    -   Databases.
    -   Machine hosting CDC.
-   Deployment with a **containerized environment**.
-   Test with **spike loads** and **concurrent data-processing
    mechanisms**.

## Assignment Outcomes

-   Present a working prototype, with Git code and documents in
    Markdown.
-   Demonstrate and explain the working prototype.
-   Present lessons learned.
-   Clearly explain which features have been considered and implemented
    and which ones have not been finished.
-   Clearly explain which code is written by the candidate and which
    code was created using AI tools.

## Architecture Overview

``` text
                         Change Data Management Service

  Configuration: connection, schedules, ...
                 |
                 v
        +-------------------------+
        | Change Data Management  |
        | Service                 |
        +-------------------------+
          |          ^          ^
          |          |          |
          |          |          +--- Excel upload via REST API
          |          +-------------- CDC webhook / pushed data
          |
          +--- Store only new data ---> Change Database (PostgreSQL)
          |
          +--- Query inventory data --> Emulated Vietful Inventory Service

  EmulatingCallbackClient --------> CDC Webhook API
  REST-based Client --------------> Excel upload
```
