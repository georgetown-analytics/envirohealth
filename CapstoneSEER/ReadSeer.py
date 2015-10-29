﻿import time
import sqlite3
import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from MasterSeer import MasterSeer
from sklearn.naive_bayes import MultinomialNB, GaussianNB, BaseDiscreteNB, BernoulliNB
import math
import itertools
from sklearn.datasets import make_classification
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.metrics import classification_report
from sklearn.feature_selection import SelectPercentile, f_classif, SelectFromModel
from sklearn.linear_model import LinearRegression, LogisticRegression, Lasso, Ridge
from sklearn.cross_validation import train_test_split, KFold
from sklearn.neighbors import KNeighborsRegressor
from sklearn.metrics import accuracy_score
from sklearn.preprocessing import normalize

class ReadSeer(MasterSeer):

    def __init__(self, path=r'.\data', testMode=False, verbose=True, sample_size=5000):

        # user supplied parameters
        self.testMode = testMode        # import one file, 500 records and return
        self.verbose = verbose          # prints status messages
        self.sample_size = sample_size  # number of rows to pull for testing

        if type(path) != str:
            raise TypeError('path must be a string')

        if path[-1] != '\\':
            path += '\\'            # if path does not end with a backslash, add one

        self.path = path

        # open connection to the database
        super().__init__(path, False, verbose=verbose)
        self.db_conn, self.db_cur = super().init_database(False)


    def __del__(self):
        self.db_conn.close()


    def describe_data(self, source = 'BREAST'):
        """ describe_data(source)
            params: source - table name in seer database, defaults to 'breast'
            returns: panda.DataFrame.describe() data

            Called from prepare_test_train_sets()
            the describe data is stored in an excel file. 
        """
        xls_name = source + '_seer_describe.xlsx'

        if self.testMode:
            df = pd.read_sql_query("SELECT * from {0} where yr_brth > 0 LIMIT 500".format(source), self.db_conn)  # speed up testing
        else:
            df = pd.read_sql_query("SELECT * from {0} where yr_brth > 0 LIMIT {1}".format(source, self.sample_size), self.db_conn)  # speed up testing


        desc = df.describe(include='all')
        exc = pd.ExcelWriter(xls_name)
        desc.to_excel(exc)
        exc.save()
        print("Data description saved to {0}".format(xls_name))
        return desc


    def get_cols(self, desc):
        """ get_cols(desc)
            params: desc - panda dataframe .describe)_ results returned rom describe_data()
            returns: list of colums

            Called from prepare_test_train_sets()
            only select fields where the 25th percentile and the 75th are different and at lease 50% of the fields have values. 
        """

        # Exclude the following fields because they have no clinical significance or they are text data. May need to code these values.
        # exclude srv_time_mon from this section since it is the variable we are testing for.
        exclude = ['SRV_TIME_MON', 'CASENUM', 'REG', 'SITEO2V', 'EOD13', 'EOD2','ICDOT10V', 'DATE_mo', 'SRV_TIME_MON_PA', 'SS_SURG', 'SURGPRIM', 'HIST_SSG_2000', 'ICD_5DIG']
        cols = []
        for field in desc:
            x = desc[field]['count']
            if desc[field]['count'] > desc['CASENUM']['count'] / 2 and \
               desc[field]['25%'] != desc[field]['75%'] and \
               field not in exclude:
                cols.append(field)
        return cols


    def prepare_test_train_sets(self, source, dependent, test_pct = .20, return_all=False, cols = []):
        """ prepare_test_train_sets(source, dependent):
            params:  source - table name in seer database, defaults to 'breast'
                     dependent - name of field we are testing for, need to remove from X and assign to Y
                     test_pct - percentage of sample to rserve for testing defaults to .20
                     return_all - return one big X, and y set for cross validation of entire sample

            returns: X_train, X_test, y_train, y_test, cols
                     X_train and X_test are pd.DataFrames, y_train and y_test are np.arrays
                     cols is a list of column names
                     if return_all, return one X, y, and cols
        """

        # get description of all fields
        desc = seer.describe_data(source)
        # select fields to test based on distribution and number of empty values
        if not cols:
            cols = seer.get_cols(desc)

        # pull relevent fields from database using random rows.
        delimList = ','.join(map(str, cols)) 
        df = pd.read_sql_query("SELECT {0}, {1} \
                                FROM {2} \
                                ORDER BY RANDOM() \
                                LIMIT {3}".format(delimList, dependent, source, self.sample_size), self.db_conn)

        self.clean_recode_data(df)

        # split data frame into train and test sets (80/20)
        if return_all:
            X = df.drop(dependent, 1)
            y = df[dependent].values
            return X, y

        X_train, X_test, y_train, y_test = train_test_split(df, df[dependent].values, test_size=test_pct, random_state=0)

        #find_features(df, X_train, y_train)
        #return

        # drop dependent colum from feature arrays
        X_train = X_train.drop(dependent, 1)
        X_test = X_test.drop(dependent, 1)

        return X_train, X_test, y_train, y_test, cols


    def test_models(self, 
                    source = 'BREAST', 
                    styles = [MultinomialNB, BernoulliNB, LinearRegression, KNeighborsRegressor, Lasso, Ridge], 
                    style_names = ['MultinomialNB', 'BernoulliNB', 'LinearRegression', 'KNeighborsRegressor', 'Lasso', 'Ridge']):

        """ test_models(source = 'BREAST'):
            params:  source - table name in seer database, defaults to 'breast'
                     styles - list of classes to use to test the data i.e. [LinearRegression, LogisticRegression]
                              if styles is left empty, default routines in function will be used.
                              make sure to import modules containing the routines to test
                                i.e. from sklearn.linear_model import LinearRegression, LogisticRegression
                     style_names - list of strings describing classes to test i.e. ['LinearRegression', 'LogisticRegression']
                     
            returns: n/a

            test various models against a combination of features, save scores to excel file named: source+'_seer_models.xlsx'
        """

        # name of excel file to dump results
        xls_name = source + '_seer_models.xlsx'
        # variable to predict
        dependent = 'SRV_TIME_MON'

        # get sets to train and test (80/20 split)
        X_train, X_test, y_train, y_test, cols = self.prepare_test_train_sets(source, dependent, test_pct = .20)

        # test 3 features at a time
        num_var = 3

        col_cnt = len(cols)
        # formula for number of combinations: nCr = n! / r! (n - r)! 
        tot_cnt = (math.factorial(col_cnt) / (math.factorial(num_var) * math.factorial(col_cnt - num_var))) * len(styles)
        print("Processing: {0} tests.".format(int(tot_cnt)))

        res = []
        counter = 0
        for style in range(len(styles)):
            style_fnc = styles[style]
            print("Testing: {0}".format(style_names[style]))
            for combo in itertools.combinations(cols, num_var):
                try: 
                    # train this model
                    x = np.array(X_train[ [k for k in combo[:num_var]] ].values).astype(np.float32)
                    X = normalize(x, axis=1, copy=True)
                    y = y_train
                    model = style_fnc()
                    model.fit(X, y)
                    #print(model.feature_log_prob_())
                    # now test and score it
                    x = np.array(X_test[ [k for k in combo[:num_var]] ].values).astype(np.float32)
                    X = normalize(x, axis=1, copy=True)
                    y = y_test
                    z = model.score(X, y)
                    res.append([z, style_names[style], [k for k in combo[:num_var]]])
                    counter += 1
                    if counter % 100 == 0:
                        print("Completed: {0}".format(counter, flush=True), end = '\r')
                except Exception as err:
                    counter += 1
                    #if self.verbose:
                    #    print(err)

        # store trial results to excel
        res = sorted(res, reverse=True)
        res_df = pd.DataFrame(res)
        exc = pd.ExcelWriter(xls_name)
        res_df.to_excel(exc)
        exc.save()

        # cross validate and plot best model
        #TODO get parameters from res
        #self.cv_model(KNeighborsRegressor, 'KNeighborsRegressor', ['DATE_yr', 'ICDOTO9V', 'ICD_5DIG'])

        print("\nAll Completed: {0}  Results stored in: {1}".format(counter, xls_name))



    def clean_recode_data(self, df):
        """ clean_recode_data(df)
            params: df - dataframe of seer data to clean
            returns: cleaned dataframe

            Each cleaning step is on its own line so we can pick and choose what 
            steps we want after we decide on variables to study

            *** This is just a starting template.
            ***   I will finish when variables are determined.
        """

        # drop all rows that have invalid or missing data
        try: 
            df = df.dropna(subset = ['YR_BRTH']) # add column names here as needed
        except: 
            pass
        try: 
            df = df[df.AGE_DX != 999] 
        except: 
            pass
        try: 
            df = df[df.SEQ_NUM != 88] 
        except: 
            pass
        try: 
            df = df[df.GRADE != 9] 
        except: 
            pass
        try: 
            df = df[df.EOD10_SZ != 999] 
        except: 
            pass
        try: 
            df = df[df.EOD10_PN < 95] 
        except: 
            pass

        df = df.fillna(0)
        return df



    def find_features(self, X, y, plot = True):
        """
            work in progress - not completed
        """
        X_indices = np.arange(X.shape[-1])

        col = list(X.columns.values)
        test = 2

        if test == 1:
            selector = SelectPercentile(f_classif, percentile=10)
            selector.fit(np.array(X), y)
            values = np.nan_to_num(selector.pvalues_)
        else:
            model = LinearRegression()
            model.fit(np.array(X), y)
            selector = SelectFromModel(f_classif)
            selector.fit(np.array(X), y)

        values = np.nan_to_num(selector.pvalues_)

        if plot:
            #scores = -np.log10(values)
            #scores /= scores.max()

            fig, ax = plt.subplots()
            #ax.set_xticks(col)
            ax.set_xticklabels(col, rotation='vertical')
            ax.set_title(r'Univariate score')

            ax.bar(X_indices - .45, values, width=.2, color='g')
            plt.show()

        for i, val in enumerate(values):
            print("{0}  {1:.2f}".format(col[i], val))

        return


    
    def cr_val_model(self, model, model_name, features, source='breast', sample_size=5000, num_folds = 5):
        """ cr_val_model(self, model, model_name, source)
            perform cross-validation on a specific model using specified sample size

            params: model - scikit-learn model function
                    model_name - string of model name
                    features = list of features(fields) to use for model
                    source - table name in seer database, defaults to 'breast'
                    num_folds - number of folds for cross validation
        """
        
        mdl = model()

        # variable to predict
        dependent = 'SRV_TIME_MON'

        # get all of the data, we will split to test/train using scikit's KFold routine
        X, y = self.prepare_test_train_sets(source, dependent, return_all=True, cols = features)
        X = np.array(X)

        kf = KFold(len(X), n_folds=num_folds, shuffle=True)
        # `means` will be a list of mean accuracies (one entry per fold)
        scores = []
        for training, testing in kf:
            # Fit a model for this fold, then apply it to the
            X = normalize(X[training], axis=1, copy=True)
            mdl.fit(X, y[training])

            X = normalize(X[testing], axis=1, copy=True)
            scores.append(mdl.score(X, y[testing]))
            y_pred_test = mdl.predict(X)

        print("Mean of scores: {:.1%}".format(np.mean(scores)))

        # TODO = plot results
        #plt.plot(xtrnp, ytrnp, 'o', label="data")
        #plt.plot(xtstp, y_pred_test, 'o', label="prediction")
        #plt.legend(loc='best')
        #plt.show()



if __name__ == '__main__':

    t0 = time.perf_counter()

    seer = ReadSeer(sample_size = 5000)
    seer.test_models()

    #seer.cv_model(LinearRegression, 'Linear Regression', ['AGE_DX', 'HISTO2V', 'HST_STGA'])
    #seer.cv_model(KNeighborsRegressor, 'KNeighborsRegressor', ['DATE_yr', 'ICDOTO9V', 'ICD_5DIG'])

    print('\nReadSeer Module Elapsed Time: {0:.2f}'.format(time.perf_counter() - t0))