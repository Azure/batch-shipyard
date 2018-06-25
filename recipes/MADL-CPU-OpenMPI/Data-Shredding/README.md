## MADL-CPU-OpenMPI Data Shredding
This Data Shredding recipe shows how to shred and deploy your training data prior to running a training job on Azure VMs via Open MPI.
Azure VMs via Open MPI.

### Data Shredding Configuration
Rename the configuration-template.json to configuration.json.  The configuration should enable the following properties:
* `node_count` should be set to the number of VMs in the compute pool.
* `thread_count` thread's count per VM.
* `training_data_shred_count` It's  advisable to set this number high. This way you only do this step once, and use it for different VMs configuration.
* 'dataset_local_directory' A local directory to download and shred the training data according to 'training_data_shred_count'.
* 'shredded_dataset_Per_Node' A local directory to hold the final data shreds before deploying them to Azure blobs. 
* 'container_name' container name where the sliced data will be stored.
* 'trainind_dataset_name' name for the dataset.  Used when creating the data blobs.
* 'subscription_id' Azure subscription id.
* 'secret_key' Azure password.
* 'resource_group' Resource group name.
* 'storage_account' storage account name and access key.
* 'training_data_container_name' Container name where the training data is hosted.
*''

You can use your own access mechanism (password, access key, etc.).  The above is only a one example.  Although, make sure to update the python script 
every time you make a configuration change.

You must agree to the following licenses prior to use:
* [High Performance ML Algorithms License](https://github.com/saeedmaleki/Distributed-Linear-Learner/blob/master/High%20Performance%20ML%20Algorithms%20-%20Standalone%20(free)%20Use%20Terms%20V2%20(06-06-18).docx)
* [TPN Ubuntu Container](https://github.com/saeedmaleki/Distributed-Linear-Learner/blob/master/TPN_Ubuntu%20Container_16-04-FINAL.docx)
* [Microsoft Third Party Notice](https://github.com/saeedmaleki/Distributed-Linear-Learner/blob/master/MicrosoftThirdPartyNotice.txt) 
