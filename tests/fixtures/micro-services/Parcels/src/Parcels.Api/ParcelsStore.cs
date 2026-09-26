using MongoDB.Driver;

namespace Parcels.Api
{
    public class ParcelsStore
    {
        private readonly IMongoCollection<Parcel> _parcels;

        public ParcelsStore(IMongoDatabase database)
            => _parcels = database.GetCollection<Parcel>("parcels");
    }
}
