"""Backward-compatible wrapper for the universal preprocessor.

Older project notes call this file for the smartphone workbook. The real
implementation now lives in preprocessing.py and reads any workbook with
Edited + Feature_data sheets.
"""

from preprocessing import main


if __name__ == "__main__":
    main()
