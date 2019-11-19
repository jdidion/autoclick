# AutoClick Changes

## 0.8.0 (2019.11.19)

* Remove `extra_click_kwargs` parameter to command/group decorator - instead, any extra keyword arguments to the decorator are passed to the Command/Group initializer.
* Add ability to automatically run a command/group when a module is called as an executable (i.e. when __name__ == "__main__") by setting `main=True` in the command/group decorator.

## 0.7.0 (2019.10.25)

* Remove support for *args and **kwargs (these never worked properly anyway)
* Add support for aggregate types
* Implement auto-conversion for dict types
* Enable type conversions to be used generically - conversions with type parameters can optionally match the generic type

## 0.6.1 (2019.09.29)

* Fix error due to difference between python 3.6 and 3.7

## 0.6.0 (2019.06.07)

* Add additional types
* Add version option
* EnumChoice: don't try to convert if the value is already an enum

## 0.5.1 (2019.04.11)

* Fix bug in get_conversion in which wrong type was being used to look up automatic conversion function

## 0.5.0 (2019.04.10)

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