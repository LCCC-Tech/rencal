# The IntermittentBucketer only pools data from the defined buckets 
# with no further discriminating features;
# It should work well with data that is independent from business processes,
# but correlated with the day of the year.

from ..weather.Bucketer import Bucketer
from ..constants import Constants

class IntermittentBucketer(Bucketer):
	def __init__(self, historical_start_date, historical_end_date, draw_period = 7, bucket_definition = Constants.MONTHLY_BUCKET_DEFINITION):
		categories = 1
		super().__init__(historical_start_date, historical_end_date, categories, draw_period, bucket_definition)


	# All data pooled in the same category, indiscriminately:
	def assign_category(self, date):
		return 0

	def tabulate_date_info(self, date):
		return [self.bucket_of(date)]