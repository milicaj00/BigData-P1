from pyspark.sql.functions import *
from pyspark.sql.types import FloatType, StringType, TimestampType, IntegerType, DoubleType, StructField, StructType, DateType
from pyspark import SparkContext, SparkConf
from pyspark.sql import SparkSession
import os
from cassandra.cluster import Cluster
import uuid

# keyspace = "bigdata"
# pollution_table = "pollution"
# traffic_table = "traffic"
# cassandra_host = "cassandra"
# cassandra_port = 9042 
# kafka_url = "kafka:9092" 
# emission_topic = "berlin-pollution"
# fcd_topic = "berlin-traffic"


emission_topic = os.getenv('POLLUTION_TOPIC')
fcd_topic = os.getenv('TRAFFIC_TOPIC')
kafka_url =  os.getenv('KAFKA_URL')

cassandra_port = os.getenv('CASSANDRA_PORT')
cassandra_host = os.getenv('CASSANDRA_HOST')
keyspace = os.getenv('CASSANDRA_KEYSPACE')
pollution_table = os.getenv('POLLUTION_TABLE')
traffic_table = os.getenv('TRAFFIC_TABLE')

vehicleSchema = StructType([
        StructField("Date", StringType()),
        StructField("LaneId", StringType()),
        StructField("VehicleCount", IntegerType())
    ])

emissionSchema = StructType([
        StructField("Date", StringType()),
        StructField("LaneId", StringType()),
        StructField("LaneCO", FloatType()),
        StructField("LaneCO2", FloatType()),
        StructField("LaneHC", FloatType()),
        StructField("LaneNOx", FloatType()),
        StructField("LanePMx", FloatType()),
        StructField("LaneNoise", FloatType()),
    ])

def writePollution(writeDF, epochId):
    print("Writting in pollution table")
    writeDF.write \
        .format("org.apache.spark.sql.cassandra") \
        .mode("append") \
        .options(table=pollution_table, keyspace=keyspace) \
        .save()
    print("Data written to Cassandra for pollution table")

def writeTraffic(writeDF, epochId):
    print("Writting in traffic table")
    writeDF.write \
        .format("org.apache.spark.sql.cassandra") \
        .mode("append") \
        .options(table=traffic_table, keyspace=keyspace) \
        .save()
    print("Data written to Cassandra for traffic table")
    

if __name__ == "__main__":

    cassandra_cluster = Cluster([cassandra_host], port=cassandra_port)
    cassandra_session = cassandra_cluster.connect()

    appName = "ConsumerApp"
    
    conf = SparkConf()
    conf.set("spark.cassandra.connection.host", cassandra_host)
    conf.set("spark.cassandra.connection.port", cassandra_port)

    conf.setMaster("local")

    spark = SparkSession.builder.config(conf=conf).appName(appName).getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")

    dfEmission = spark \
        .readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", kafka_url) \
        .option("subscribe", emission_topic) \
        .load()

    dfFcd = spark \
        .readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", kafka_url) \
        .option("subscribe", fcd_topic) \
        .load()
    
    dfEmissionParsed = dfEmission.selectExpr("CAST(value AS STRING)").select(from_json(col("value"), emissionSchema).alias("data")).select("data.*")

    dfFcdParsed = dfFcd.selectExpr("CAST(value AS STRING)").select(from_json(col("value"), vehicleSchema).alias("data")).select("data.*")
    

    dfEmissionParsed = dfEmissionParsed.withColumnRenamed("Date", "date") \
                         .withColumnRenamed("LaneId", "laneid") \
                         .withColumnRenamed("LaneCO", "laneco") \
                         .withColumnRenamed("LaneCO2", "laneco2") \
                         .withColumnRenamed("LaneHC", "lanehc") \
                         .withColumnRenamed("LaneNOx", "lanenox") \
                         .withColumnRenamed("LanePMx", "lanepmx") \
                         .withColumnRenamed("LaneNoise", "lanenoise")


    dfEmissionParsed = dfEmissionParsed.withColumn("id", expr("uuid()"))


    dfFcdParsed = dfFcdParsed.withColumnRenamed("Date", "date") \
                                .withColumnRenamed("LaneId", "laneid") \
                                .withColumnRenamed("VehicleCount", "vehiclecount")
    

    dfFcdParsed = dfFcdParsed.withColumn("id", expr("uuid()"))



    query_traffic = dfFcdParsed.writeStream \
        .foreachBatch(writeTraffic) \
        .outputMode("append") \
        .start()

    query_pollution = dfEmissionParsed.writeStream \
        .foreachBatch(writePollution) \
        .outputMode("append") \
        .start()

    print("PRINTING TRAFFIC DATA")
    query_traffic2 = dfFcdParsed.writeStream \
    .outputMode("append") \
    .format("console") \
    .start()

    
    print("PRINTING POLLUTION DATA")
    query_pollution2 = dfEmissionParsed.writeStream \
        .outputMode("append") \
        .format("console") \
        .start()

    query_traffic.awaitTermination()
    query_pollution.awaitTermination()
    query_pollution2.awaitTermination()
    query_traffic2.awaitTermination()

    # spark.streams.awaitAnyTermination()
    spark.stop()   