# AutoClick Changes

## 0.5.0 (Unpublished)

* Breaking change: Major refactoring to split up core.py and make import graph acyclic
* Add defaults for validations.Defined
* Breaking change: Rename validations.ge_defined to validations.defined_ge

## 0.4.0 (2019.04.09)

* Add additional types (DelimitedList) and validations (SequenceLength)
* Add decorator for conversions that can be automatically applied based on the parameter type

## 0.3.0 (2019.03.29)

* Handle tuple types for which the desired default value is `None` (rather than a sequence of `None`s)
* Make ValidationError inherit from UsageError
* Fix Defined validations
* By default do not create an instance of a composite types if none of its parameters are defined

## 0.2.3 (2019.01.15)

* Add generic GLOBAL_OPTIONS
* Fix handling of collection types
* Add new Mutex validation
* Add ability to pass function/class to be decorted to most decorators
* Fix argument parsing when using prefixes for composite types

## 0.2.2 (2018.12.30)

* Fix pass_context
* Fix AutoClickGroup parse_args()

## 0.2.1 (2018.12.18)

* Add pass_context to command() and group() decorators

## 0.2.0 (2018.12.18)

* Code reorg
* Name change to autoclick
* Better support for composites

## 0.1.0 (2018.12.04)

* Initial release