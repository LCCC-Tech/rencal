import datetime

class Bucketer:
    """
    The Bucketer deals with certain sampling for our simulation engine to build future data timeseries from past data.
    We use this approach for inputs whose distribution is largely correlated with the calendar date.

    Bucketer is the parent class of all other such utility classes, and serves as a main interface as well as providing general functionality.

    Once this date-assignment step is complete, the data structure is queried at runtime by the simulation engine.
    It uses this structure to pool a random date of a particular kind, and use this as the starting date of a ``draw_Period``-sized sample to patch the future with.
    This mechanism of building a full future sample is automated in the ``random_Sample()`` method, that returns the start of all consecutive draw periods as an enumeration of datetime.datetime objects.

    Attributes:
        _historical_Start_Date (datetime.datetime): A date containing the midnight (start) of the first day for which we have historical data available.
        _historical_End_Date (datetime.datetime): A date containing the midnight (start) of the last day for which we have historical data available.
        _categories (int): Represents the number of categories the bucketer needs for additional filtering.
        _draw_Period (int): Continuous days sampled at once starting from the date pooled by each iteration of the loop in ``random_Sample()``.
        _bucket_Definition (list): A sorted list of :class:`ShortDates` that completely partitions the year into buckets, each bucket being represented by the range of dates between two :class:`ShortDates`.
        _bucket_Structure (dict): A dictionary of categories, each with its own bucket structure where buckets are filled with dates from that particular category, according to the bucket definition.
        _lookup_Structure (dict): A dictionary of all dates in the bucket structure, each with a tabulated date information.

    """
    def __init__(self, historical_start_date, historical_end_date, categories, draw_period, bucket_definition):
        """
        In initializing a Bucketer, we build a hierarchical data structure called the bucket_Structure that is the core of this class.
        The bucket_Structure contains all individual calendar dates between the historical_Start_Date and historical_End_Date inclusive, each filtered through 2 layers of logic, ``bucket_of()`` and ``assign_Category()``, that assign it to a particular "category" and "bucket".

        - The "category" is a placeholder descriptor of the date for when children classes need an additional level of sieving.
        - The "bucket" is refering to the position of that date in the ``bucket_Definition``, a custom partition of the year specified by an ordered list of :class:`ShortDate` objects (calendar month/day pairs).
        
        These are both represented by consecutive integers starting at ``0``.

        Args:
            historical_start_date (datetime.datetime): A date containing the midnight (start) of the first day for which we have historical data available.
            historical_end_date (datetime.datetime): A date containing the midnight (start) of the last day for which we have historical data available.
            categories (int): Represents the number of categories the bucketer needs for additional filtering.
            draw_period (int): Continuous days sampled at once starting from the date pooled by each iteration of the loop in ``random_Sample()``.
            bucket_definition (list): A sorted list of :class:`ShortDates` that completely partitions the year into buckets, each bucket being represented by the range of dates between two :class:`ShortDates`.
        """
        if not historical_start_date <= historical_end_date:
            raise ValueError("Historical dates are not ordered") 
        # A datatime.datetime object containing the midnight (start) of the first day for which we have historical data available
        self._historical_start_date = historical_start_date
        # A datatime.datetime object containing the midnight (start) of the last day for which we have historical data available
        self._historical_end_date = historical_end_date

        # Represents the number of categories the bucketer needs for additional filtering
        self._categories = categories

        if not type(bucket_definition) == list:
            raise TypeError("The bucket definition provided is not a list")
        if not len(bucket_definition) >= 2:
            raise ValueError("The bucket definition does not define a proper partition of a year")
        if not all(bucket_definition[i] < bucket_definition[i + 1] for i in range(len(bucket_definition) - 1)):
            raise ValueError("The bucket definition is not strictly ordered so does not define mutually exclusive year partitions")
        if not all((bucket_definition[i + 1] - bucket_definition[i]) >= draw_period for i in range(len(bucket_definition) - 1)):
            raise ValueError("There is a bucketed interval that is smaller that the days we are drawing by")
        # Continuous days sampled at once starting from the date pooled by each iteration of the loop in random_Sample()
        self._draw_period = draw_period
        # A sorted list of ShortDates that completely partitions the year into buckets, each bucket being represented by the range of dates between 2 ShortDates
        self._bucket_definition = bucket_definition

        # A dictionary of categories, each with its own bucket structure where buckets are filled with dates from that particular category, according to the bucket definition
        self._bucket_structure = {category: {bucket: [] for bucket in range(0, len(self.bucket_definition))} for category in range(self._categories)}
        self._lookup_structure = {}

        # Fills the bucket_structure
        self.populate_buckets()

    @property
    def historical_start_date(self):
        return self._historical_start_date

    @property
    def historical_end_date(self):
        return self._historical_end_date

    @property
    def categories(self):
        return self._categories

    @property
    def draw_period(self):
        return self._draw_period

    @property
    def bucket_definition(self):
        return self._bucket_definition

    @property
    def bucket_structure(self):
        return self._bucket_structure

    @property
    def lookup_structure(self):
        return self._lookup_structure


    def bucket_of(self, start_of_draw_period):
        """
        Associates a set of ``draw_period`` days with a bucket number. Uses memoization to speed up lookup of previously determined bucket numbers.

        Args:
            start_of_draw_period (datetime.datetime): A date representing the start of a "drawing period" (a ``draw_period``-day interval starting at the date in question).

        Returns:
            bucket (int): A bucket's number to represent where to draw from or in which bucket to store this "drawing period".
        """
        try:
            return self.lookup_structure[start_of_draw_period][0]
        except KeyError:
            # Keeping a reference of where our binary search is restricted to in the sorted bucket definition partition
            start_index = 0
            end_index = len(self.bucket_definition) - 1

            # Adding to the start of draw period to allow for accurate bucketing of draw periods that are on the border between buckets
            # This also allows us to obtain a leap day when needed, without compromising the ShortDate functionality
            days_offset = int(self.draw_period / 2) 
            offset_draw_period = start_of_draw_period + datetime.timedelta(days = days_offset)

            # This date is in the bucket that loops around the list, spanning two years
            if (offset_draw_period < self.bucket_definition[start_index] or offset_draw_period >= self.bucket_definition[end_index]):
                return len(self.bucket_definition) - 1

            # Binary lookup in sorted bucket_definition otherwise
            while start_index != end_index:

                middle_index = start_index + int((end_index - start_index) / 2)
                search_target_start = self.bucket_definition[middle_index]
                search_target_end = self.bucket_definition[middle_index + 1] # We can do this without fear of IndexException because we have eliminated this case in the if statement above the while block

                if (offset_draw_period >= search_target_start):
                    start_index = middle_index
                    if (offset_draw_period < search_target_end):
                        return middle_index
                else:
                    end_index = middle_index

    def assign_category(self, date):
        """
        Always implemented in the child classes.
        Expects a :class:`datetime.datetime` object representing the start of a "drawing period" (a ``draw_Period``-day interval starting at the date in question).
        Returns a category's number.

        Args:
            date (datetime.datetime): A date representing the start of a "drawing period" (a ``draw_Period``-day interval starting at the date in question).
        """
        raise NotImplementedError

    def tabulate_date_info(self, date):
        """
        Always implemented in the child classes.
        Used to memorize information about a date in the lookup structure.

        Args:
            date (datetime.datetime): A date representing the start of a "drawing period" (a ``draw_Period``-day interval starting at the date in question).
        """
        raise NotImplementedError
    
    def populate_buckets(self):
        """
        Utility function that runs once in the constructor, saving all relevant dates in their appropriate buckets, filling the ``bucket_structure`` accordingly.
        """
        # We run through all available historical data (bar the last days that would not fit if we started a draw period then)
        for date in [self.historical_start_date + datetime.timedelta(days) for days in range((self.historical_end_date - datetime.timedelta(self.draw_period - 2) - self.historical_start_date).days)]:
            # Getting the right list in the bucket structure:
            bucket = self.bucket_of(date)
            category = self.assign_category(date)

            self.lookup_structure[date] = self.tabulate_date_info(date)
            self.bucket_structure[category][bucket].append(date)

        # Picking off where we left off the last loop to fill the table with future dates as well:
        for future_date in [date + datetime.timedelta(days + 1) for days in range((datetime.datetime.today() + datetime.timedelta(365 * 6) - date).days)]:

            self.lookup_structure[future_date] = self.tabulate_date_info(future_date)


    # Called by the simulation engine with the datetime.datetime edges of the future period as parameters;
    # Returns a list of randomly selected datetime.datetime objects that would fill the future period if sampled draw_period-days at a time starting at each of them and stiching it all together:
    def random_sample(self, future_start_date, future_end_date, rng_python):
        """
        Fills a specified future period with randomly selected dates from the bucket structure, matching the future period across buckets and categories.

        Args:
            future_start_date (datetime.datetime): The start of the future period.
            future_end_date (datetime.datetime): The end of the future period.
            rng_python (random.Random): A random number generator object.

        Returns:
            sample (list): A list of randomly selected :class"`datetime.datetime` objects that would fill the future period if sampled ``draw_period``-days at a time starting at each of them and stiching it all together.
        """

        sample = []
        date = future_start_date 

        while date <= future_end_date - datetime.timedelta(self.draw_period - 1): # Still in range for a full draw period remaining
            # Getting the right list in the bucket structure:
            bucket = self.bucket_of(date)
            category = self.assign_category(date)
            index = rng_python.randint(0, len(self.bucket_structure[category][bucket]) - 1)

            sample.append(self.bucket_structure[category][bucket][index])

            # Going through the future interval in draw_period-day increments
            date += datetime.timedelta(self.draw_period)

        return sample
