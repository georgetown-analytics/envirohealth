﻿#SEER database
# SEER data should be loaded into the Data sub-directory of this project.
#
#  .\Data
#    \incidence
#       read.seer.research.nov14.sas       <- Data Dictionary
#       *.txt                              <- Data files in fixed width text format
#    \populations
#
# regex to read data dictionary
# \s+@\s+([0-9]+)\s+([A-Z0-9_]*)\s+[$a-z]+([0-9]+)\.\s+/\* (.+?(?= \*/))

import re
import time
import os
import sqlite3
import glob

# database file name on disk
DB_NAME = 'seer.db'
#data dictionary fields
DD_OFFSET  = 0
DD_COLNAME = 1
DD_LENGTH  = 2

class LoadSeerData:

    def __init__(self, path = r'.\data', reload = True, testMode = False, verbose = True, batch = 5000):

        # user supplied paramters
        self.reload = reload        # deletes and recreates db before start of loading data. 
        self.testMode = testMode    # import one file, 100 records and return
        self.verbose = verbose      # prints status messages
        self.batchSize = batch      # number of rows to commit to db in one transation

        if type(path) != str:
            raise TypeError('path must be a string')

        if path[-1] != '\\':
            path += '\\'            # if path does not end with a backslash, add one

        self.path = path

        # used to read in data dictionary, used to parse actual data files.
        self.SeerDataDictRegexPat = '\s+@\s+([0-9]+)\s+([A-Z0-9_]*)\s+[$a-z]+([0-9]+)\.\s+/\* (.+?(?=\*/))'

        # List to hold lists of [Column Offset, Column Name, Column Length]
        self.dataDictInfo = []

        # open connection to the database
        self.init_database(self.reload)


    def init_database(self, reload):
        try:
            if reload:
                os.remove(self.path + DB_NAME)

            #initialize database
            self.db_conn = sqlite3.connect(self.path + DB_NAME)
            self.db_cur = self.db_conn.cursor()

            if self.verbose:
                print('Database initialized')
        except Exception as e:
            print('ERROR connecting to the database: ' + e.strerror)
            raise(e)


    def load_data_dictionary(self, fname = r'incidence\read.seer.research.nov14.sas'):
        if self.verbose:
            print('\nStart Load of Data Dictionary')

        # pre-compile regex to improve performance in loop
        reCompiled = re.compile(self.SeerDataDictRegexPat)

        t0 = time.perf_counter()

        with open(self.path + fname) as fDataDict:
            for line in fDataDict:
                fields = reCompiled.match(line)
                if fields:
                    # change to 0 offset, Data Dict entry starts at 1
                    # Column Offset, Column Name, Column Length
                    self.dataDictInfo.append([int(fields.groups()[DD_OFFSET])-1, fields.groups()[DD_COLNAME], int(fields.groups()[DD_LENGTH])])

        if self.verbose:
            print('Data Dictionary loaded in {0:5.4f} sec.'.format(time.perf_counter() - t0))


    # supports specific file or wildcard filename to import all data in one call.
    # path specified is off of the path sent in the constructor so actual filename will be self.path + fname
    def load_data(self, fname = r'incidence\yr1973_2012.seer9\breast.txt'):
        try:
            self.load_data_dictionary()
        except Exception as e:
            print('ERROR loading data dictionary.')
            raise(e)

        if len(self.dataDictInfo) == 0:
            raise('Bad Data Dictionary Data')

        # create the table in the db
        self.create_table()

        timeStart = time.perf_counter()

        totRows = 0
        for fileName in glob.glob(self.path + fname):
            totRows += self.load_one_file(fileName)

        if self.verbose:
            print('Loading Data completed.\n Rows Imported: {0:d} in {1:.1f} seconds.\n Loaded {2:.1f} per sec.'.format(totRows, time.perf_counter() - timeStart, (totRows / (time.perf_counter() - timeStart))))


    def load_one_file(self, fname):
        if self.verbose:
            print('\nStart Loading Data: {}'.format(fname))

        # Need to get the name of the SEER text file so we can store it into the SOURCE field.
        fileSource = os.path.basename(fname)
        fileSource = os.path.splitext(fileSource)[0]
        
        # pre-build the sql statement outside of the loop so it is only called once
        #   get list of field names for INSERT statement
        fieldList = ','.join(map(str, [row[DD_COLNAME] for row in self.dataDictInfo])) 

        sqlCommand = 'INSERT INTO seer(SOURCE,' + fieldList + ') values (' + '?,' * len(self.dataDictInfo) + '?)'

        # create variables needed in loop
        rowValues = []               # hold one records values
        multipleRowValues = []       # hold batchSize lists of rowValues to commit to DB in one transaction
        totRows = 0                   

        # open SEER fixed width text file
        with open(fname, 'r') as fData:
            
            for line in fData:
                totRows += 1
                rowValues.clear()
                rowValues.append(fileSource)  # first field is the SEER data file name i.e. breast or respir

                # iterate through all of the fields in the text file and store to rowValues list
                for fldNum in range(len(self.dataDictInfo)):
                    #field = line[self.dataDictInfo[fldNum][0]:self.dataDictInfo[fldNum][0]+self.dataDictInfo[fldNum][2]]
                    rowValues.append( line[self.dataDictInfo[fldNum][DD_OFFSET] : self.dataDictInfo[fldNum][DD_OFFSET] + self.dataDictInfo[fldNum][DD_LENGTH]] )

                # store this one row list of values to the list of lists for batch insert
                multipleRowValues.append(rowValues)

                # commit to DB in batchSize batches to speed performance
                if totRows % self.batchSize == 0:
                    self.db_cur.executemany(sqlCommand, multipleRowValues)
                    self.db_conn.commit()
                    multipleRowValues.clear()
                    if self.verbose:
                        print('', end='.', flush=True)

                # if in testMode, exit loop after 100 records are stored
                if totRows > 100 and self.testMode:
                    self.db_cur.executemany(sqlCommand, multipleRowValues)
                    self.db_conn.commit()
                    break

        if self.verbose:
            print('\n - Loading completed. Rows Imported: {0:d}'.format(totRows))

        return totRows


    def create_table(self):
        # Create the table from the fields read from data dictionary and stored in self.dataDictInfo
        # Make list comma delimited
        delimList = ','.join(map(str, [row[DD_COLNAME] for row in self.dataDictInfo])) 

        # create the table
        self.db_conn.execute('create table seer(SOURCE,' + delimList + ')')
                            
    def __str__(self, **kwargs):
        pass


if __name__ == '__main__':

    t0 = time.perf_counter();
    seer = LoadSeerData(testMode = False)
    p = seer.load_data(r'incidence\yr1973_2012.seer9\breast.txt')  # load one file
    
    #seer = LoadSeerData(testMode = False)
    #p = seer.load_data(r'incidence\yr1973_2012.seer9\*.txt')   # load all files

    print('\nModule Elapsed Time: {0:.2f}'.format(time.perf_counter() - t0))